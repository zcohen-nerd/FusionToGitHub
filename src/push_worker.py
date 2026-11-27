"""Run a planned push on a background thread (decision Q6). No Fusion dependency.

Fusion's API may only be used on its main thread: Autodesk's threading
guide says not to call any Fusion API function from a worker thread, and
that even ``messageBox`` can crash Fusion there. So the worker never touches
Fusion. Everything it has to say leaves through one callable, ``post``,
as a JSON-serialisable dict; the add-in's ``fusion_bridge`` forwards those
to Fusion's main thread with a custom event and answers questions back
through :meth:`PushWorker.answer`.

Messages (every one has ``type``, ``job`` and an increasing ``seq``):

``step``     ``text``: what the push is doing now.
``tick``     sent about every 0.5 s while the push runs, so the main thread
             can check the progress dialog's Cancel button.
``confirm``  ``id``, ``text``: a Yes/No question. The worker waits for
             ``answer(id, yes)``; no answer within ``confirm_timeout``
             seconds, a cancel, or a shutdown all count as No.
``warn``     ``text``: a warning to show; the push carries on.
``error``    ``text``: an error to show; the push will end without success.
``done``     ``result``: push_export's result (a dict, ``{"cancelled": True,
             ...}``, or None when git failed and said why in ``error``).
``failed``   ``error``: an unexpected exception, with secrets redacted.

``done`` or ``failed`` is always the last message of a job, and the
single-push guard (``is_busy``) is already released when it is sent.
"""

from __future__ import annotations

import itertools
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

from .fusion_git_core import redact_secrets

CONFIRM_TIMEOUT_SECONDS = 10 * 60
TICK_SECONDS = 0.5

Post = Callable[[Dict[str, Any]], Any]

_guard = threading.Lock()
_active: Optional["PushWorker"] = None
_job_ids = itertools.count(1)


class WorkerBusy(RuntimeError):
    """A push is already running; only one may run at a time."""


def is_busy() -> bool:
    """True while a push is running (from start() until just before its last message)."""
    with _guard:
        return _active is not None


def active_worker() -> Optional["PushWorker"]:
    with _guard:
        return _active


def shutdown_active(timeout: float = 5.0) -> bool:
    """Cancel the running push, if any, and wait up to *timeout* s. True if none is left running."""
    worker = active_worker()
    return worker.shutdown(timeout) if worker else True


class WorkerGitUI:
    """fusion_git_core's GitUI for the worker thread: posts instead of showing."""

    def __init__(self, worker: "PushWorker"):
        self._worker = worker

    def info(self, message: str) -> None:
        if self._worker.logger:
            self._worker.logger.info(message)

    def warn(self, message: str) -> None:
        if self._worker.logger:
            self._worker.logger.warning(message)
        self._worker.post_message({"type": "warn", "text": redact_secrets(message)})

    def error(self, message: str) -> None:
        if self._worker.logger:
            self._worker.logger.error(message)
        self._worker.post_message({"type": "error", "text": redact_secrets(message)})

    def confirm(self, message: str) -> bool:
        return self._worker.ask(redact_secrets(message))


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class PushWorker:
    """One background push: ``controller.execute(plan, ...)`` on a daemon thread."""

    def __init__(
        self,
        controller: Any,
        plan: Any,
        post: Post,
        logger: Optional[logging.Logger] = None,
        *,
        confirm_timeout: float = CONFIRM_TIMEOUT_SECONDS,
        tick_seconds: float = TICK_SECONDS,
        on_finish: Optional[Callable[[], None]] = None,
    ):
        self.controller = controller
        self.plan = plan
        self.logger = logger
        self.job = next(_job_ids)
        self._post = post
        self._confirm_timeout = confirm_timeout
        self._tick_seconds = tick_seconds
        self._on_finish = on_finish
        self._cancel = threading.Event()
        self._finished = threading.Event()  # the push itself has returned
        self._closing = False
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self._questions = itertools.count(1)
        self._pending: Dict[int, List[Any]] = {}  # id -> [event, answer]
        self._thread: Optional[threading.Thread] = None
        self._ticker: Optional[threading.Thread] = None

    # -- main-thread API ------------------------------------------------------

    def start(self) -> "PushWorker":
        """Start the push. Raises WorkerBusy if another push is running."""
        global _active
        with _guard:
            if _active is not None:
                raise WorkerBusy("A push is already running.")
            _active = self
        try:
            self._thread = threading.Thread(target=self._run, name=f"PushToGitHub-push-{self.job}", daemon=True)
            self._ticker = threading.Thread(target=self._tick, name=f"PushToGitHub-tick-{self.job}", daemon=True)
            # The ticker first: a push that ends at once must find it started.
            self._ticker.start()
            self._thread.start()
        except BaseException:
            with _guard:
                _active = None
            raise
        return self

    def cancel(self) -> None:
        """Ask the push to stop; any open question is answered No."""
        self._cancel.set()
        self._release_questions()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def answer(self, request_id: int, yes: bool) -> bool:
        """Answer question *request_id*. False if it is no longer waiting (timed out, cancelled)."""
        with self._lock:
            entry = self._pending.get(request_id)
            if entry is None:
                return False
            entry[1] = bool(yes)
            entry[0].set()
            return True

    def shutdown(self, timeout: float = 5.0) -> bool:
        """Cancel, release open questions as No, and wait up to *timeout* s. True if it ended."""
        self._closing = True
        self.cancel()
        for thread in (self._thread, self._ticker):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout)
        return not self.is_alive()

    def is_alive(self) -> bool:
        return any(t is not None and t.is_alive() for t in (self._thread, self._ticker))

    # -- worker-thread side ---------------------------------------------------

    def post_message(self, message: Dict[str, Any]) -> bool:
        """Send one message to the main thread. Never raises; False if it couldn't be sent."""
        with self._lock:
            message = dict(message, job=self.job, seq=next(self._seq))
        try:
            return self._post(message) is not False
        except Exception:
            if self.logger:
                self.logger.exception("Couldn't pass a push message to Fusion")
            return False

    def ask(self, text: str) -> bool:
        """Ask the main thread a Yes/No question and wait for the answer (No on timeout)."""
        if self._cancel.is_set() or self._closing:
            return False
        event = threading.Event()
        with self._lock:
            request_id = next(self._questions)
            self._pending[request_id] = [event, False]
        try:
            if not self.post_message({"type": "confirm", "id": request_id, "text": text}):
                return False
            if not event.wait(self._confirm_timeout):
                if self.logger:
                    self.logger.warning("No answer to a question within %s s; treated as No.", self._confirm_timeout)
                return False
            with self._lock:
                return bool(self._pending[request_id][1])
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _release_questions(self) -> None:
        with self._lock:
            for entry in self._pending.values():
                entry[1] = False
                entry[0].set()

    def _tick(self) -> None:
        while not self._finished.wait(self._tick_seconds):
            self.post_message({"type": "tick", "cancel_requested": self._cancel.is_set()})

    def _run(self) -> None:
        global _active
        terminal: Dict[str, Any]
        try:
            result = self.controller.execute(
                self.plan, WorkerGitUI(self), on_step=self._step, cancel=self._cancel
            )
            terminal = {"type": "done", "result": _jsonable(result)}
        except Exception as exc:
            if self.logger:
                self.logger.exception("Background push failed")
            terminal = {"type": "failed", "error": redact_secrets(f"{type(exc).__name__}: {exc}")}
        finally:
            # Whatever happens here, the single-push guard is released.
            try:
                self._finished.set()
                self._release_questions()
                ticker = self._ticker
                if ticker is not None and ticker.ident is not None and ticker is not threading.current_thread():
                    ticker.join(max(self._tick_seconds * 4, 2.0))
                if self._on_finish is not None:
                    self._on_finish()
            except Exception:
                if self.logger:
                    self.logger.exception("Clean-up after the push failed")
            finally:
                with _guard:
                    if _active is self:
                        _active = None
        self.post_message(terminal)

    def _step(self, text: str) -> None:
        self.post_message({"type": "step", "text": redact_secrets(text)})


__all__ = [
    "CONFIRM_TIMEOUT_SECONDS",
    "TICK_SECONDS",
    "PushWorker",
    "WorkerBusy",
    "WorkerGitUI",
    "active_worker",
    "is_busy",
    "shutdown_active",
]
