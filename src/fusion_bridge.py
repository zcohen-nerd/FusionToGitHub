"""Fusion's main thread side of a background push (decision Q6).

``push_worker`` runs git on a background thread and must never call Fusion.
This module is the other half: it registers a Fusion custom event, and the
worker's ``post`` becomes ``app.fireCustomEvent(id, json)``, which is safe
from any thread. Fusion then calls ``PushEventHandler.notify`` on its main
thread, where the progress dialog, questions and the final summary are
shown (Autodesk's "Working in a Separate Thread" guide).

Only one push runs at a time (``push_worker.is_busy``). The dialog has
closed by the time the push runs, so a job carries the plain data needed for
the summary, never a reference to the dialog or its inputs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import adsk.core

from push_worker import PushWorker, WorkerBusy

EVENT_SUFFIX = "_PushWorker"
SHUTDOWN_TIMEOUT_SECONDS = 3.0
PROGRESS_TITLE = "Fusion → GitHub"

NOTHING_PUSHED = "Push cancelled — nothing was pushed."
BUSY_TEXT = (
    "A push is already running. Wait for it to finish (or press Cancel in its progress window), "
    "then push again."
)


@dataclass
class PushJob:
    """What the summary needs once the dialog has closed. Plain data."""

    repo_name: str
    exported_names: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# -- texts (no Fusion calls) --------------------------------------------------


def success_text(repo_name: str, git_result: Dict[str, Any], exported_names, warnings) -> str:
    branch = git_result.get("branch", "<unknown>")
    commit_short = (git_result.get("commit") or "")[:7]
    lines = [
        f"✅ Pushed to GitHub, branch: {branch}" + (f" (commit {commit_short})" if commit_short else ""),
        f"Settings for '{repo_name}' updated.",
    ]
    if exported_names:
        lines += ["", "Exported files:"] + [f" • {name}" for name in exported_names]
    notes = []
    if git_result.get("reused_branch"):
        notes.append("Added a new commit to the existing branch.")
    if git_result.get("bootstrapped"):
        notes.append(
            f"The repository was empty, so a first commit was added to '{git_result.get('base_branch') or 'main'}'."
        )
    notes.append("Your local repository folder was not changed.")
    lines += ["", "Git flow details:"] + [f" • {note}" for note in notes]
    if warnings:
        lines += ["", "Warnings:"] + [f" • {w}" for w in warnings]
    return "\n".join(lines)


def cancelled_text(result: Dict[str, Any]) -> str:
    """Say plainly what a cancelled push did, using push_export's cancellation result."""
    if result.get("published"):
        commit_short = (result.get("commit") or "")[:7]
        where = f"branch {result.get('branch')}" + (f" (commit {commit_short})" if commit_short else "")
        return (
            "Push cancelled, but GitHub had already received this export: it is on "
            f"{where}. There is no need to push it again."
        )
    if result.get("uncertain"):
        return (
            "Push cancelled while sending to GitHub, and it couldn't be checked whether the export "
            "arrived. Look at the repository on GitHub before pushing again."
        )
    if result.get("repository_initialized"):
        return (
            "Push cancelled. The empty GitHub repository received its first commit, but this "
            "export was not pushed."
        )
    return NOTHING_PUSHED


def failed_text(git_result_missing: bool, warnings, error: str = "") -> str:
    if git_result_missing:
        lines = ["Git operations failed. See the messages above for details."]
    else:
        lines = [
            "The push stopped because of an unexpected error:",
            error,
            "",
            "Check the repository on GitHub before pushing again; the log file has the details.",
        ]
    if warnings:
        lines += ["", "Warnings:"] + [f" • {w}" for w in warnings]
    return "\n".join(lines)


# -- the bridge -----------------------------------------------------------------


class PushEventHandler(adsk.core.CustomEventHandler):
    """Runs on Fusion's main thread for every message the worker posts."""

    def __init__(self, bridge: "WorkerBridge"):
        super().__init__()
        self.bridge = bridge

    def notify(self, args):
        # An exception escaping a Fusion event handler is swallowed by Fusion
        # and can leave the push looking stuck; log it instead.
        try:
            self.bridge.handle(args.additionalInfo)
        except Exception:
            if self.bridge.logger:
                self.bridge.logger.exception("PushEventHandler failed")


class WorkerBridge:
    """Owns the custom event, the running worker and its progress dialog."""

    def __init__(self, app, ui, event_id: str, title: str, logger: Optional[logging.Logger] = None):
        self.app = app
        self.ui = ui
        self.event_id = event_id
        self.title = title
        self.logger = logger
        self.registered = False
        self._event = None
        self._handler: Optional[PushEventHandler] = None
        self.worker: Optional[PushWorker] = None
        self.job: Optional[PushJob] = None
        self.progress = None
        self._cancel_shown = False

    # -- lifetime (main thread) ------------------------------------------------

    def register(self) -> bool:
        """Register the custom event. Called from the add-in's run()."""
        if self.registered:
            return True
        try:
            event = self.app.registerCustomEvent(self.event_id)
        except Exception:
            # Left registered by an earlier copy of this add-in that didn't stop cleanly.
            try:
                self.app.unregisterCustomEvent(self.event_id)
                event = self.app.registerCustomEvent(self.event_id)
            except Exception:
                if self.logger:
                    self.logger.exception("Couldn't register the custom event %s", self.event_id)
                return False
        if not event:
            return False
        handler = PushEventHandler(self)
        event.add(handler)
        # Fusion keeps only a weak reference to handlers: hold this one.
        self._event, self._handler = event, handler
        self.registered = True
        return True

    def close(self, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> bool:
        """Stop the running push (if any), then release the event. True if no push is left running."""
        stopped = True
        if self.worker is not None:
            stopped = self.worker.shutdown(timeout)
            if not stopped and self.logger:
                self.logger.warning("The background push did not stop within %.0f s.", timeout)
        self._hide_progress()
        self.worker = None
        self.job = None
        if self.registered:
            try:
                if self._event is not None and self._handler is not None:
                    self._event.remove(self._handler)
            except Exception:
                pass
            try:
                self.app.unregisterCustomEvent(self.event_id)
            except Exception:
                if self.logger:
                    self.logger.exception("Couldn't unregister the custom event %s", self.event_id)
        self.registered = False
        self._event = self._handler = None
        return stopped

    @property
    def busy(self) -> bool:
        """True from start() until the job's last message has been handled."""
        return self.job is not None

    def start(self, controller, plan, job: PushJob, on_finish: Optional[Callable[[], None]] = None) -> PushWorker:
        """Start a background push. Raises WorkerBusy if one is running (or RuntimeError)."""
        if not self.registered:
            raise RuntimeError("The add-in's background push isn't available. Restart the add-in and try again.")
        if self.job is not None:
            raise WorkerBusy(BUSY_TEXT)
        worker = PushWorker(controller, plan, self.post, self.logger, on_finish=on_finish)
        self.job, self.worker = job, worker
        self._cancel_shown = False
        self._show_progress("Pushing to GitHub…")
        try:
            worker.start()
        except BaseException:
            self.job = self.worker = None
            self._hide_progress()
            raise
        return worker

    # -- any thread -----------------------------------------------------------------

    def post(self, message: Dict[str, Any]) -> bool:
        """The worker's ``post``: queue *message* for Fusion's main thread."""
        if not self.registered:
            return False
        return bool(self.app.fireCustomEvent(self.event_id, json.dumps(message)))

    # -- main thread ------------------------------------------------------------------

    def handle(self, payload: str) -> None:
        message = json.loads(payload or "{}")
        worker = self.worker
        if worker is None or message.get("job") != worker.job:
            return  # from a push that was shut down; nothing to show
        kind = message.get("type")
        if kind == "tick":
            self._check_cancel()
        elif kind == "step":
            if self.progress is not None and not worker.cancel_requested:
                self.progress.message = message.get("text", "")
        elif kind == "confirm":
            self._hide_progress()
            answer = self.ui.messageBox(
                message.get("text", ""), self.title, adsk.core.MessageBoxButtonTypes.YesNoButtonType
            )
            worker.answer(message.get("id"), answer == adsk.core.DialogResults.DialogYes)
            self._show_progress(self._progress_message())
        elif kind in ("warn", "error"):
            self._hide_progress()
            self.ui.messageBox(message.get("text", ""), self.title)
            self._show_progress(self._progress_message())
        elif kind in ("done", "failed"):
            self._finish(message)

    def _check_cancel(self) -> None:
        progress = self.progress
        if progress is None or self.worker is None or self.worker.cancel_requested:
            return
        if progress.wasCancelled:
            if self.logger:
                self.logger.info("Push cancelled by the user")
            self.worker.cancel()
            progress.message = "Cancelling…"

    def _progress_message(self) -> str:
        return "Cancelling…" if self.worker is not None and self.worker.cancel_requested else "Pushing to GitHub…"

    def _show_progress(self, text: str) -> None:
        try:
            if self.progress is None:
                self.progress = self.ui.createProgressDialog()
                self.progress.isBackgroundTranslucencyEnabled = True
                self.progress.cancelButtonText = "Cancel"
            self.progress.show(PROGRESS_TITLE, text, 0, 1, 0)
        except Exception:
            if self.logger:
                self.logger.exception("Couldn't show the push progress")

    def _hide_progress(self) -> None:
        if self.progress is None:
            return
        try:
            if self.progress.isShowing:
                self.progress.hide()
        except Exception:
            pass

    def _finish(self, message: Dict[str, Any]) -> None:
        job = self.job or PushJob(repo_name="")
        self._hide_progress()
        self.progress = None
        self.job = self.worker = None
        if message.get("type") == "failed":
            text = failed_text(False, job.warnings, message.get("error", ""))
        else:
            result = message.get("result")
            if not result:
                text = failed_text(True, job.warnings)
            elif result.get("cancelled"):
                text = cancelled_text(result)
            else:
                text = success_text(job.repo_name, result, job.exported_names, job.warnings)
        if self.logger:
            self.logger.info("Push finished: %s", text.splitlines()[0])
        self.ui.messageBox(text, self.title)


__all__ = [
    "BUSY_TEXT",
    "EVENT_SUFFIX",
    "NOTHING_PUSHED",
    "PushEventHandler",
    "PushJob",
    "WorkerBridge",
    "WorkerBusy",
    "cancelled_text",
    "failed_text",
    "success_text",
]
