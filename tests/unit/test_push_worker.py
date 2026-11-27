"""The background push worker (S4, decision Q6). No Fusion: messages go to a queue.

Real threads throughout. Every wait is bounded, and each test checks that the
worker's threads have ended and the single-push guard is free afterwards.
"""

import os
import queue
import tempfile
import threading
import time
import unittest
from unittest import mock

import _paths
from test_core_cancel_hooks import write_hook
from test_core_identity_history import GitSandbox

import push_worker
from credentials import MemoryCredentialStore
from push_controller import PushController, PushPlan
from settings_store import SettingsStore

WAIT = 30  # seconds; upper bound for any single wait in these tests
TOKEN = "ghp_" + "z" * 36


def worker_threads():
    return [t for t in threading.enumerate() if t.name.startswith("PushToGitHub-") and t.is_alive()]


class Inbox:
    """Collects posted messages; answers questions with *answers* (or never, if None)."""

    def __init__(self, answers=None):
        self.queue = queue.Queue()
        self.received = []
        self.answers = answers
        self.worker = None

    def post(self, message):
        self.queue.put(message)
        return True

    def run_until_done(self, timeout=WAIT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self.received.append(message)
            if message["type"] == "confirm" and self.answers is not None:
                self.worker.answer(message["id"], self.answers.pop(0))
            if message["type"] in ("done", "failed"):
                return message
        raise AssertionError(f"no done/failed within {timeout} s: {self.received}")

    def types(self, include_ticks=False):
        return [m["type"] for m in self.received if include_ticks or m["type"] != "tick"]


class ScriptedController:
    """Stands in for PushController.execute: runs *script(plan, ui, on_step, cancel)*."""

    def __init__(self, script):
        self.script = script

    def execute(self, plan, ui, on_step=None, cancel=None):
        return self.script(plan, ui, on_step, cancel)


class WorkerTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self._check_nothing_left_running)

    def _check_nothing_left_running(self):
        push_worker.shutdown_active(10)
        self.assertFalse(push_worker.is_busy())
        self.assertEqual(worker_threads(), [])

    def start(self, script, answers=None, **kw):
        inbox = Inbox(answers)
        worker = push_worker.PushWorker(ScriptedController(script), "plan", inbox.post, **kw)
        inbox.worker = worker
        worker.start()
        return worker, inbox


class MessageTests(WorkerTestCase):
    def test_messages_arrive_in_order_and_done_is_last(self):
        def script(plan, ui, on_step, cancel):
            on_step("Fetching")
            ui.info("only logged")
            ui.warn(f"watch out https://u:{TOKEN}@github.com/x")
            time.sleep(0.7)  # long enough for a tick
            on_step("Pushing")
            ui.error("it broke")
            return {"branch": "b", "commit": "c" * 40}

        worker, inbox = self.start(script, tick_seconds=0.2)
        done = inbox.run_until_done()
        self.assertEqual(inbox.types(), ["step", "warn", "step", "error", "done"])
        self.assertIn("tick", inbox.types(include_ticks=True))
        self.assertEqual(done["result"], {"branch": "b", "commit": "c" * 40})
        seqs = [m["seq"] for m in inbox.received]
        self.assertEqual(seqs, sorted(seqs))
        self.assertTrue(all(m["job"] == worker.job for m in inbox.received))
        self.assertNotIn(TOKEN, str(inbox.received))
        # The guard is already free when "done" is handled.
        self.assertFalse(push_worker.is_busy())

    def test_confirm_round_trip_yes_and_no(self):
        answers = []

        def script(plan, ui, on_step, cancel):
            answers.append(ui.confirm("First?"))
            answers.append(ui.confirm("Second?"))
            return {"answers": list(answers)}

        worker, inbox = self.start(script, answers=[True, False])
        done = inbox.run_until_done()
        self.assertEqual(done["result"], {"answers": [True, False]})
        questions = [m for m in inbox.received if m["type"] == "confirm"]
        self.assertEqual([q["text"] for q in questions], ["First?", "Second?"])
        self.assertNotEqual(questions[0]["id"], questions[1]["id"])
        self.assertFalse(worker.answer(questions[0]["id"], True))  # no longer waiting

    def test_an_unanswered_question_times_out_as_no(self):
        def script(plan, ui, on_step, cancel):
            return {"answer": ui.confirm("Anyone there?")}

        started = time.monotonic()
        worker, inbox = self.start(script, answers=None, confirm_timeout=0.5)
        done = inbox.run_until_done()
        self.assertEqual(done["result"], {"answer": False})
        self.assertLess(time.monotonic() - started, 10)

    def test_a_question_that_cannot_be_delivered_is_no_at_once(self):
        def script(plan, ui, on_step, cancel):
            return {"answer": ui.confirm("Hello?")}

        results = queue.Queue()

        def post(message):
            results.put(message)
            return message["type"] != "confirm"  # e.g. the custom event was unregistered

        worker = push_worker.PushWorker(ScriptedController(script), "plan", post, confirm_timeout=60)
        worker.start()
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            message = results.get(timeout=WAIT)
            if message["type"] == "done":
                break
        self.assertEqual(message["result"], {"answer": False})

    def test_an_exception_becomes_failed_with_secrets_redacted(self):
        finished = []

        def script(plan, ui, on_step, cancel):
            raise RuntimeError(f"fatal: https://bob:{TOKEN}@github.com/a/b.git")

        worker, inbox = self.start(script, on_finish=lambda: finished.append(True))
        failed = inbox.run_until_done()
        self.assertEqual(failed["type"], "failed")
        self.assertIn("RuntimeError", failed["error"])
        self.assertNotIn(TOKEN, failed["error"])
        self.assertEqual(finished, [True])
        self.assertFalse(push_worker.is_busy())

    def test_a_non_exception_ending_still_reports_failed(self):
        # Found in the S4 review: SystemExit (not an Exception) skipped the
        # last message, so Fusion would think the push was still running.
        def script(plan, ui, on_step, cancel):
            raise SystemExit(3)

        worker, inbox = self.start(script)
        failed = inbox.run_until_done()
        self.assertEqual(failed["type"], "failed")
        self.assertIn("stopped unexpectedly", failed["error"])
        self.assertIs(worker.terminal_delivered, True)
        self.assertFalse(push_worker.is_busy())

    def test_a_result_that_cannot_be_delivered_is_recorded_and_logged(self):
        def script(plan, ui, on_step, cancel):
            return {"ok": True}

        logger = mock.Mock()
        worker = push_worker.PushWorker(ScriptedController(script), "plan",
                                        lambda message: message["type"] not in ("done", "failed"), logger)
        worker.start()
        self.assertTrue(worker.shutdown(WAIT) or not worker.is_alive())
        self.assertIs(worker.terminal_delivered, False)
        logger.error.assert_called_once()
        self.assertIn("couldn't be passed to Fusion", logger.error.call_args[0][0])

    def test_a_failing_post_or_clean_up_never_stops_the_worker(self):
        def script(plan, ui, on_step, cancel):
            on_step("step")
            return {"ok": True}

        def post(message):
            raise OSError("Fusion went away")

        def broken_cleanup():
            raise OSError("locked")

        worker = push_worker.PushWorker(ScriptedController(script), "plan", post, on_finish=broken_cleanup)
        worker.start()
        self.assertTrue(worker.shutdown(WAIT) or not worker.is_alive())
        self.assertFalse(push_worker.is_busy())


class GuardAndShutdownTests(WorkerTestCase):
    def blocking(self, release):
        def script(plan, ui, on_step, cancel):
            # Waits for the test or for a cancel, never longer than WAIT.
            deadline = time.monotonic() + WAIT
            while not release.is_set() and not cancel.is_set() and time.monotonic() < deadline:
                time.sleep(0.02)
            return {"cancelled": True} if cancel.is_set() else {"ok": True}

        return script

    def test_a_second_push_is_refused_while_one_runs(self):
        release = threading.Event()
        worker, inbox = self.start(self.blocking(release))
        self.assertTrue(push_worker.is_busy())
        self.assertIs(push_worker.active_worker(), worker)
        second = push_worker.PushWorker(ScriptedController(self.blocking(release)), "plan", Inbox().post)
        with self.assertRaises(push_worker.WorkerBusy):
            second.start()
        self.assertFalse(second.is_alive())
        release.set()
        self.assertEqual(inbox.run_until_done()["result"], {"ok": True})
        # Free again: the next push may start.
        worker2, inbox2 = self.start(lambda *a: {"ok": 2})
        self.assertEqual(inbox2.run_until_done()["result"], {"ok": 2})

    def test_cancel_reaches_the_running_push(self):
        worker, inbox = self.start(self.blocking(threading.Event()))
        self.assertFalse(worker.cancel_requested)
        worker.cancel()
        self.assertTrue(worker.cancel_requested)
        self.assertEqual(inbox.run_until_done()["result"], {"cancelled": True})

    def test_shutdown_releases_an_open_question_and_ends_the_threads(self):
        folder = tempfile.mkdtemp(prefix="ftg_worker_")
        self.addCleanup(_paths.force_rmtree, folder)
        asked = threading.Event()

        def script(plan, ui, on_step, cancel):
            asked.set()
            return {"answer": ui.confirm("Waiting forever?")}

        worker, inbox = self.start(script, answers=None, confirm_timeout=WAIT,
                                   on_finish=lambda: _paths.force_rmtree(folder))
        self.assertTrue(asked.wait(WAIT))
        time.sleep(0.2)  # the question is being waited on
        started = time.monotonic()
        self.assertTrue(worker.shutdown(10))
        self.assertLess(time.monotonic() - started, 10)
        self.assertFalse(worker.is_alive())
        self.assertFalse(os.path.exists(folder))
        self.assertEqual(inbox.run_until_done()["result"], {"answer": False})
        self.assertFalse(worker.ask("After shutdown?"))  # never waits once closing

    def test_shutdown_active_without_a_push(self):
        self.assertTrue(push_worker.shutdown_active(1))
        self.assertIsNone(push_worker.active_worker())


class RealGitCancelTests(GitSandbox, WorkerTestCase):
    """Cancelling a real push through the worker: before and after GitHub accepted it."""

    def setUp(self):
        GitSandbox.setUp(self)  # doesn't chain to WorkerTestCase.setUp, so:
        self.addCleanup(self._check_nothing_left_running)  # runs before the sandbox is removed
        store = SettingsStore(os.path.join(self.base, "settings.json"))
        store.load()
        self.controller = PushController(store, MemoryCredentialStore())

    def plan(self, content):
        return PushPlan(
            profile_name="Designs", repo_path=self.work,
            exports=[(self.export("a.step", content), "Part/a.step")],
            message_template="note", design_name="Part", identity=self.identity,
        )

    def run_push(self, content, cancel_when=None):
        inbox = Inbox()
        worker = push_worker.PushWorker(self.controller, self.plan(content), inbox.post)
        inbox.worker = worker
        worker.start()
        if cancel_when is not None:
            deadline = time.monotonic() + WAIT
            while not cancel_when() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(cancel_when(), "the hook never started")
            worker.cancel()
        return inbox.run_until_done()

    def hook(self, name, marker, body):
        write_hook(self.origin, name, f'touch "{marker.replace(chr(92), "/")}"\n{body}')

    def test_cancel_before_github_accepted_the_push(self):
        first = self.run_push("first")
        self.assertFalse(first["result"].get("cancelled"), first)
        marker = os.path.join(self.base, "pre-receive.ran")
        self.hook("pre-receive", marker, "sleep 30\nexit 1")
        started = time.monotonic()
        done = self.run_push("second", cancel_when=lambda: os.path.exists(marker))
        self.assertLess(time.monotonic() - started, 25)
        result = done["result"]
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["published"])
        self.assertFalse(result["uncertain"])
        heads = self.remote_heads()
        self.assertEqual(len([h for h in heads if h.startswith("fusion-export/")]), 1, heads)

    def test_cancel_after_github_accepted_the_push(self):
        first = self.run_push("first")
        self.assertFalse(first["result"].get("cancelled"), first)
        marker = os.path.join(self.base, "post-receive.ran")
        self.hook("post-receive", marker, "sleep 30")
        done = self.run_push("second", cancel_when=lambda: os.path.exists(marker))
        result = done["result"]
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["published"], result)
        tip = __import__("fusion_git_core").git_run(self.origin, "rev-parse", result["branch"]).stdout.strip()
        self.assertEqual(tip, result["commit"])

    def remote_heads(self):
        proc = __import__("fusion_git_core").git_run(self.origin, "branch", "--format", "%(refname:short)")
        return proc.stdout.split()


if __name__ == "__main__":
    unittest.main()
