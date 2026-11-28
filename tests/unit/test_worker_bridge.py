"""Background pushes end to end: dialog → worker thread → custom event → main thread.

Driven through the SIMULATED Fusion API. Custom events fired by the worker
are queued and only delivered when the test runs ``app.process_events`` on
the main thread, as Fusion's message loop would. The harness fails any test
that leaves a push or worker thread running, or that calls the Fusion UI from
another thread.
"""

import gc
import json
import os
import time
import unittest
from unittest import mock

import _paths  # noqa: F401
from addin_harness import AddinTestCase, DialogResults, worker_threads

from test_core_cancel_hooks import write_hook

import fusion_bridge
import fusion_git_core as core
import push_worker
import Push_To_GitHub as addin

YES, NO = DialogResults.DialogYes, DialogResults.DialogNo
TOKEN = "ghp_" + "k" * 36


class BridgeTestCase(AddinTestCase):
    def setUp(self):
        super().setUp()
        self.seed({"Designs": self.work_profile(publicationNoticeAccepted=True)},
                  meta={"lastSelectedRepo": "Designs"})
        self.design("Bracket")

    def first_push(self):
        """An ordinary push, so the empty "GitHub" repository has a main branch."""
        command = self.open_dialog()
        self.assertFalse(self.push(command).executeFailed, self.ui.texts())
        self.assertIn("Backed up \"Bracket\" to GitHub.", self.last_message())

    def start_push_held_by_hook(self, hook, body):
        """Start a push that the remote holds in *hook*; return once the hook is running."""
        marker = os.path.join(self.base, f"{hook}.ran")
        write_hook(self.origin, hook, f'touch "{marker.replace(chr(92), "/")}"\n{body}')
        command = self.open_dialog()
        args = self.press_ok(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        self.assertTrue(command.isTerminated)  # the dialog has closed; git is still running
        self.app.process_events(timeout=30, until=lambda: os.path.exists(marker))
        self.assertTrue(addin.bridge.busy)
        return command

    def press_progress_cancel(self):
        progress = addin.bridge.progress
        self.assertTrue(progress.isShowing)
        self.assertEqual(progress.cancelButtonText, "Cancel")
        progress.press_cancel()


class ProgressAndSummaryTests(BridgeTestCase):
    def test_progress_steps_then_the_summary(self):
        command = self.open_dialog()
        args = self.push(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        progress = [p for p in self.ui.progress_dialogs if p.cancelButtonText == "Cancel"][-1]
        self.assertFalse(progress.isShowing)
        self.assertIn("Pushing to GitHub…", progress.shown)
        self.assertTrue(len(progress.messages) >= 2, progress.messages)  # git steps arrived
        self.assertIn("Saved to: fusion-export/Bracket-", self.last_message())
        self.assertIn("Your files and branches in the local repository folder weren't changed.", self.last_message())
        self.assertFalse(addin.bridge.busy)
        self.assertFalse(push_worker.is_busy())

    def test_document_closed_during_the_push_changes_nothing(self):
        command = self.open_dialog()
        self.press_ok(command)
        self.app.activeProduct = None  # the user closed the design; the worker never asks Fusion
        self.wait_for_push()
        self.assertIn("Backed up \"Bracket\" to GitHub.", self.last_message())

    def test_exported_files_are_removed_after_the_push(self):
        command = self.open_dialog()
        self.press_ok(command)
        export_dir = os.path.dirname(addin.bridge.worker.plan.exports[0][0])
        self.assertTrue(os.path.isdir(export_dir))  # still there while git reads it
        self.wait_for_push()
        self.assertFalse(os.path.exists(export_dir))

    def test_unexpected_worker_error_is_reported_redacted(self):
        command = self.open_dialog()
        boom = RuntimeError(f"fatal: https://x:{TOKEN}@github.com/a.git")
        with mock.patch("push_controller.PushController.execute", side_effect=boom):
            self.assertFalse(self.push(command).executeFailed)
        self.assertIn("unexpected error", self.last_message())
        self.assertNotIn(TOKEN, self.last_message())
        self.assertFalse(push_worker.is_busy())

    def test_warnings_from_the_worker_are_shown_on_the_main_thread(self):
        # A token in the push address: warned about (by the worker), then the
        # push to this unreachable address fails.
        core.git_run(self.work, "remote", "set-url", "--push", "origin",
                     f"https://user:{TOKEN}@example.invalid/acme/designs.git")
        command = self.open_dialog()
        self.push(command)
        self.assertIn("The backup didn't complete", self.last_message())
        texts = "\n".join(self.ui.texts())
        self.assertIn("contains a password or token", texts)
        self.assertNotIn(TOKEN, texts)


class QuestionTests(BridgeTestCase):
    def test_reusing_a_branch_is_asked_on_the_main_thread(self):
        self.first_push()
        command = self.open_dialog()
        command.commandInputs.itemById("branchPreview").value = "main"
        self.answer(YES)  # add this export to the main branch?
        self.assertFalse(self.push(command).executeFailed)
        self.assertTrue(any("main branch" in q for q in self.ui.questions), self.ui.questions)
        self.assertIn("Saved to: main", self.last_message())

    def test_declining_branch_reuse_pushes_nothing(self):
        self.first_push()
        before = core.git_run(self.origin, "rev-parse", "main").stdout
        command = self.open_dialog()
        command.commandInputs.itemById("branchPreview").value = "main"
        self.answer(NO)
        self.push(command)
        self.assertEqual(self.last_message(), fusion_bridge.NOTHING_PUSHED)
        self.assertEqual(core.git_run(self.origin, "rev-parse", "main").stdout, before)

    def test_large_files_are_confirmed_once_before_the_push_starts(self):
        with mock.patch.object(core, "SIZE_WARN_BYTES", 1):
            command = self.open_dialog()
            self.answer(YES)  # these exports are large: push anyway?
            self.assertFalse(self.push(command).executeFailed, self.ui.texts())
        large = [q for q in self.ui.questions if "exports are large" in q]
        self.assertEqual(len(large), 1)  # asked on the main thread, not again by the worker
        self.assertIn("Backed up \"Bracket\" to GitHub.", self.last_message())

    def test_declining_large_files_keeps_the_dialog_open(self):
        with mock.patch.object(core, "SIZE_WARN_BYTES", 1):
            command = self.open_dialog()
            self.answer(NO)
            args = self.press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertFalse(command.isTerminated)
        self.assertEqual(self.last_message(), fusion_bridge.NOTHING_PUSHED)
        self.assertFalse(push_worker.is_busy())
        self.assertEqual(self.remote_branches(), [])

    def test_too_large_files_are_refused_before_the_push_starts(self):
        with mock.patch.object(core, "SIZE_BLOCK_BYTES", 1):
            command = self.open_dialog()
            args = self.press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("GitHub rejects files of 100 MB or more", self.last_message())
        self.assertFalse(push_worker.is_busy())


class CancelTests(BridgeTestCase):
    def test_cancel_before_github_accepted_says_nothing_was_pushed(self):
        self.first_push()
        branches_before = self.remote_branches()
        self.start_push_held_by_hook("pre-receive", "sleep 30\nexit 1")
        started = time.monotonic()
        self.press_progress_cancel()
        self.wait_for_push(timeout=30)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(self.last_message(), fusion_bridge.NOTHING_PUSHED)
        self.assertEqual(self.remote_branches(), branches_before)

    def test_cancel_after_github_accepted_says_it_was_published(self):
        self.first_push()
        self.start_push_held_by_hook("post-receive", "sleep 30")
        self.press_progress_cancel()
        self.wait_for_push(timeout=30)
        text = self.last_message()
        self.assertIn("GitHub had already received this export", text)
        self.assertIn("fusion-export/Bracket-", text)

    def test_cancel_texts_distinguish_every_case(self):
        self.assertEqual(fusion_bridge.cancelled_text({"cancelled": True}), fusion_bridge.NOTHING_PUSHED)
        self.assertEqual(fusion_bridge.cancelled_text({"cancelled": True, "published": False}),
                         fusion_bridge.NOTHING_PUSHED)
        published = fusion_bridge.cancelled_text(
            {"cancelled": True, "published": True, "branch": "b", "commit": "abcdef123"})
        self.assertIn("already received", published)
        self.assertIn("b (commit abcdef1)", published)
        self.assertIn("couldn't be checked", fusion_bridge.cancelled_text({"cancelled": True, "uncertain": True}))
        self.assertIn("first commit", fusion_bridge.cancelled_text(
            {"cancelled": True, "repository_initialized": True}))

    def test_a_second_push_is_refused_while_one_runs(self):
        self.first_push()
        self.start_push_held_by_hook("pre-receive", "sleep 30\nexit 1")
        second = self.open_dialog()
        args = self.press_ok(second)
        self.assertTrue(args.executeFailed)
        self.assertFalse(second.isTerminated)  # the dialog stays open
        self.assertEqual(self.last_message(), fusion_bridge.BUSY_TEXT)
        self.press_progress_cancel()
        self.wait_for_push(timeout=30)
        self.assertEqual(self.last_message(), fusion_bridge.NOTHING_PUSHED)

    def test_a_late_message_from_an_earlier_push_is_ignored(self):
        # Found in the S4 test review: nothing proved a "done" from a push
        # that was shut down can't finish (or answer) the push now running.
        self.first_push()
        self.start_push_held_by_hook("pre-receive", "sleep 30\nexit 1")
        bridge = addin.bridge
        shown = len(self.ui.messages)
        bridge.handle(json.dumps({"type": "done", "job": bridge.worker.job - 1,
                                  "result": {"branch": "stale", "commit": "0" * 40}}))
        bridge.handle(json.dumps({"type": "confirm", "job": bridge.worker.job - 1, "id": 1, "text": "stale?"}))
        self.assertTrue(bridge.busy)
        self.assertTrue(bridge.progress.isShowing)
        self.assertEqual(len(self.ui.messages), shown)
        self.press_progress_cancel()
        self.wait_for_push(timeout=30)
        self.assertEqual(self.last_message(), fusion_bridge.NOTHING_PUSHED)

    def test_the_bridge_itself_refuses_a_second_push(self):
        # The dialog checks first; the bridge must refuse too (a race past
        # the dialog's check), keep the running job, and clean up the export.
        self.first_push()
        self.start_push_held_by_hook("pre-receive", "sleep 30\nexit 1")
        bridge = addin.bridge
        running = bridge.job
        with self.assertRaises(push_worker.WorkerBusy):
            bridge.start(bridge.worker.controller, bridge.worker.plan, fusion_bridge.PushJob(repo_name="x"))
        self.assertIs(bridge.job, running)
        second = self.open_dialog()
        with mock.patch.object(push_worker, "is_busy", return_value=False), \
                mock.patch.object(fusion_bridge.WorkerBridge, "busy", new_callable=mock.PropertyMock,
                                  return_value=False):
            args = self.press_ok(second)
        self.assertTrue(args.executeFailed)
        self.assertEqual(self.last_message(), fusion_bridge.BUSY_TEXT)
        self.assertIs(bridge.job, running)
        self.press_progress_cancel()
        self.wait_for_push(timeout=30)

    def test_a_push_whose_result_was_lost_no_longer_blocks_new_pushes(self):
        # Found in the S4 review: if the last message can't reach Fusion,
        # every later push used to be refused until the add-in restarted.
        command = self.open_dialog()
        real_post = addin.bridge.post

        def lose_the_result(message):
            return False if message.get("type") in ("done", "failed") else real_post(message)

        with mock.patch.object(addin.bridge, "post", side_effect=lose_the_result):
            self.press_ok(command)
            push_worker.shutdown_active(30)
        self.assertIs(addin.bridge.worker.terminal_delivered, False)
        self.assertFalse(addin.bridge.busy)  # the lost job is dropped
        self.assertFalse(self.push(self.open_dialog()).executeFailed, self.ui.texts())
        self.assertIn("Backed up \"Bracket\" to GitHub.", self.last_message())

    def test_a_message_box_that_lets_the_push_finish_leaves_no_progress_window(self):
        # Fusion may keep delivering events while a message box is open: the
        # push can finish during a warning. The progress window must then
        # not be shown again for a push that has ended (S4 review).
        core.git_run(self.work, "remote", "set-url", "--push", "origin",
                     f"https://user:{TOKEN}@example.invalid/acme/designs.git")
        command = self.open_dialog()
        self.ui.while_message_box_open = lambda: self.app.process_events(
            timeout=60, until=lambda: not addin.bridge.busy)
        self.push(command)
        self.assertFalse(addin.bridge.busy)
        self.assertIsNone(addin.bridge.progress)
        self.assertFalse(any(p.isShowing for p in self.ui.progress_dialogs))
        self.assertIn("The backup didn't complete", "\n".join(self.ui.texts()))

    def test_stop_during_a_push_ends_it_and_leaves_nothing_behind(self):
        self.first_push()
        self.start_push_held_by_hook("pre-receive", "sleep 30\nexit 1")
        export_dir = os.path.dirname(addin.bridge.worker.plan.exports[0][0])
        bridge = addin.bridge
        started = time.monotonic()
        addin.stop(None)
        self.assertLess(time.monotonic() - started, 15)
        # The worker is told to stop at once; give its thread a bounded moment to finish.
        push_worker.shutdown_active(15)
        self.assertEqual(worker_threads(), [])
        self.assertFalse(push_worker.is_busy())
        self.assertFalse(os.path.exists(export_dir))
        self.assertEqual(self.app.registered_custom_events, [])
        self.assertFalse(bridge.post({"type": "tick"}))  # nothing reaches Fusion any more
        shown = len(self.ui.messages)
        self.app.process_events(timeout=0.5)
        self.assertEqual(len(self.ui.messages), shown)  # no summary after stop


class EventTests(AddinTestCase):
    def test_messages_from_an_old_job_or_after_close_are_ignored(self):
        addin.run(None)
        bridge = addin.bridge
        bridge.handle(json.dumps({"type": "done", "job": 999, "result": {"branch": "x"}}))
        self.assertEqual(self.ui.messages, [])
        event_id = addin.CMD_ID + fusion_bridge.EVENT_SUFFIX
        self.assertTrue(self.app.fireCustomEvent(event_id, "{}"))
        self.assertEqual(self.app.process_events(timeout=0.5), 1)
        addin.stop(None)
        self.assertFalse(self.app.fireCustomEvent(event_id, "{}"))

    def test_the_custom_event_handler_survives_garbage_collection(self):
        addin.run(None)
        gc.collect()
        event_id = addin.CMD_ID + fusion_bridge.EVENT_SUFFIX
        seen = []
        with mock.patch.object(addin.bridge, "handle", side_effect=seen.append):
            self.app.fireCustomEvent(event_id, '{"type": "tick"}')
            self.app.process_events(timeout=1)
        self.assertEqual(seen, ['{"type": "tick"}'])

    def test_handler_exceptions_are_logged_not_raised(self):
        addin.run(None)
        event_id = addin.CMD_ID + fusion_bridge.EVENT_SUFFIX
        self.app.fireCustomEvent(event_id, "not json")
        self.assertEqual(self.app.process_events(timeout=1), 1)  # did not raise

    def test_without_the_custom_event_the_push_is_refused_and_the_dialog_stays_open(self):
        self.seed({"Designs": self.work_profile(publicationNoticeAccepted=True)},
                  meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        addin.bridge.close()
        args = self.press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("background push isn't available", self.last_message())


class StandInFidelityTests(unittest.TestCase):
    """The simulated Fusion API is as strict as the behaviour the add-in relies on."""

    def setUp(self):
        import adsk.core

        self.core = adsk.core
        self.app = adsk.core.Application.reset()

    def test_custom_events_are_queued_never_delivered_inside_fire(self):
        import threading

        event = self.app.registerCustomEvent("E")
        seen = []

        class Handler(self.core.CustomEventHandler):
            def notify(self, args):
                seen.append((args.additionalInfo, threading.get_ident()))

        handler = Handler()
        event.add(handler)
        worker = threading.Thread(target=lambda: self.app.fireCustomEvent("E", "from worker"))
        worker.start()
        worker.join(10)
        self.assertEqual(seen, [])  # not delivered on the worker thread
        self.assertEqual(self.app.process_events(timeout=1), 1)
        self.assertEqual(seen, [("from worker", threading.get_ident())])
        self.assertFalse(self.app.fireCustomEvent("unknown", ""))
        with self.assertRaises(RuntimeError):
            self.app.registerCustomEvent("E")
        self.assertTrue(self.app.unregisterCustomEvent("E"))
        with self.assertRaises(TimeoutError):
            self.app.process_events(timeout=0.2, until=lambda: False)

    def test_ui_calls_from_another_thread_are_refused_and_recorded(self):
        import threading

        errors = []

        def call():
            try:
                self.app.userInterface.messageBox("hi")
            except RuntimeError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=call)
        thread.start()
        thread.join(10)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(self.app.thread_violations), 1)

    def test_value_types_and_progress_arguments(self):
        inputs = self.core.CommandInputs()
        text = inputs.addStringValueInput("s", "S", "")
        flag = inputs.addBoolValueInput("b", "B", True, "", False)
        with self.assertRaises(TypeError):
            text.value = None
        with self.assertRaises(TypeError):
            flag.value = 1
        progress = self.app.userInterface.createProgressDialog()
        with self.assertRaises(TypeError):
            progress.show("t", "m", 0, 2.5, 0)
        with self.assertRaises(AssertionError):
            progress.press_cancel()  # not showing
        progress.show("t", "m", 0, 2, 0)
        progress.press_cancel()
        self.assertTrue(progress.wasCancelled)

    def test_ok_ends_the_command_and_fires_destroy_and_validate_inputs(self):
        definition = self.app.userInterface.commandDefinitions.addButtonDefinition("C", "C", "")
        command = self.app.userInterface.open_command("C")
        fired = []

        class Recorder:
            def __init__(self, name):
                self.name = name

            def notify(self, args):
                fired.append(self.name)

        recorders = [Recorder("changed"), Recorder("validate"), Recorder("destroy")]
        command.inputChanged.add(recorders[0])
        command.validateInputs.add(recorders[1])
        command.destroy.add(recorders[2])
        command.commandInputs.addStringValueInput("s", "S", "")
        self.core.change_input(command, "s", value="x")
        self.assertEqual(fired, ["changed", "validate"])
        self.assertFalse(self.core.press_ok(command).executeFailed)
        self.assertEqual(fired[-1], "destroy")
        self.assertTrue(command.isTerminated)
        with self.assertRaises(AssertionError):
            self.core.press_ok(command)
        other = self.app.userInterface.open_command("C")
        self.core.press_cancel(other)
        self.assertTrue(other.isTerminated)
        self.assertTrue(definition.isValid)


if __name__ == "__main__":
    unittest.main()
