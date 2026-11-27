"""Add-in start/stop and handler lifetime, against the SIMULATED Fusion API."""

import gc
import unittest
from unittest import mock

import _paths  # noqa: F401
import adsk
import adsk.core
from addin_harness import AddinTestCase

import Push_To_GitHub as addin
import push_dialog


class LifecycleTests(AddinTestCase):
    def controls(self):
        found = []
        for i in range(self.ui.allToolbarPanels.count):
            panel = self.ui.allToolbarPanels.item(i)
            control = panel.controls.itemById(addin.CONTROL_ID)
            if control:
                found.append((panel.id, control))
        return found

    def test_run_adds_one_promoted_button(self):
        addin.run(None)
        self.assertIsNotNone(self.ui.commandDefinitions.itemById(addin.CMD_ID))
        controls = self.controls()
        self.assertEqual([panel for panel, _ in controls], ["SolidUtilitiesAddinsPanel"])
        self.assertTrue(controls[0][1].isPromoted)
        self.assertEqual(adsk.auto_terminate_calls[-1], False)
        self.assertEqual(len(addin.handlers), 1)

    def test_running_twice_or_restarting_never_duplicates_the_button(self):
        addin.run(None)
        addin.run(None)
        self.assertEqual(len(self.controls()), 1)
        addin.stop(None)
        addin.run(None)
        self.assertEqual(len(self.controls()), 1)
        self.assertEqual(self.ui.commandDefinitions.count, 1)

    def test_a_leftover_control_from_a_crash_is_replaced(self):
        # This copy created them in an earlier load that never reached stop().
        definition = self.ui.commandDefinitions.addButtonDefinition(addin.CMD_ID, addin.CMD_NAME, "", "")
        self.ui.allToolbarPanels.item(0).controls.addCommand(definition, addin.CONTROL_ID)
        addin._command_owners()[addin.CMD_ID] = addin.THIS_FILE
        addin.run(None)
        self.assertEqual(len(self.controls()), 1)
        self.assertFalse(definition.isValid)  # replaced by a fresh definition
        self.assertIsNot(self.ui.commandDefinitions.itemById(addin.CMD_ID), definition)
        self.assertEqual(self.ui.messages, [])

    def test_a_second_installed_copy_warns_once_and_adds_no_button(self):
        # Another copy (any version) of the add-in already owns the button.
        other = self.ui.commandDefinitions.addButtonDefinition(addin.CMD_ID, addin.CMD_NAME, "", "")
        other_control = self.ui.allToolbarPanels.item(0).controls.addCommand(other, addin.CONTROL_ID)
        addin.run(None)
        self.assertIn("Another copy of 'Push to GitHub' is already running", self.last_message())
        self.assertEqual(len(self.ui.messages), 1)
        self.assertIsNone(addin.bridge)
        self.assertEqual(self.app.registered_custom_events, [])
        self.assertEqual([c for _, c in self.controls()], [other_control])
        addin.run(None)
        self.assertEqual(len(self.ui.messages), 1)  # warned once
        addin.stop(None)
        # stop() leaves the other copy's button and command alone.
        self.assertTrue(other.isValid and other_control.isValid)
        self.assertIs(self.ui.commandDefinitions.itemById(addin.CMD_ID), other)

    def test_repeated_run_and_stop_keep_one_button_and_one_custom_event(self):
        event_id = addin.CMD_ID + "_PushWorker"
        for _ in range(3):
            addin.run(None)
            addin.run(None)
            self.assertEqual(len(self.controls()), 1)
            self.assertEqual(self.ui.commandDefinitions.count, 1)
            self.assertEqual(self.app.registered_custom_events, [event_id])
            self.assertEqual(len(addin.handlers), 1)
            addin.stop(None)
            self.assertEqual(self.controls(), [])
            self.assertEqual(self.app.registered_custom_events, [])
            self.assertIsNone(addin.bridge)
            self.assertNotIn(addin.CMD_ID, addin._command_owners())
        addin.stop(None)  # a second stop is harmless

    def test_handlers_survive_garbage_collection(self):
        addin.run(None)
        gc.collect()
        command = self.ui.open_command(addin.CMD_ID)  # commandCreated still reaches the add-in
        self.assertIsNotNone(command.commandInputs.itemById("repoSelector"))
        gc.collect()
        adsk.core.change_input(command, "commitMsgPush", value="x")  # dialog handlers held too
        self.assertEqual(len(command.inputChanged.handlers), 1)

    def test_the_stand_in_drops_handlers_nobody_holds(self):
        # Control for the test above: Fusion keeps only weak references.
        event = adsk.core.Event()
        event.add(adsk.core.CustomEventHandler())
        gc.collect()
        self.assertEqual(event.handlers, [])

    def test_stop_removes_button_definition_and_all_handlers(self):
        addin.run(None)
        self.ui.open_command(addin.CMD_ID)
        self.assertEqual(len(addin.dialog_handlers), 2)
        addin.stop(None)
        self.assertEqual(self.controls(), [])
        self.assertEqual(self.app.registered_custom_events, [])
        self.assertIsNone(self.ui.commandDefinitions.itemById(addin.CMD_ID))
        self.assertEqual(addin.handlers, [])
        self.assertEqual(addin.dialog_handlers, [])
        self.assertIsNone(addin.logger)

    def test_fallback_panel_when_the_add_ins_panel_is_missing(self):
        self.ui.allToolbarPanels.items = [p for p in self.ui.allToolbarPanels.items if p.id != addin.PANEL_ID]
        addin.run(None)
        self.assertEqual([panel for panel, _ in self.controls()], [addin.FALLBACK_PANEL_ID])

    def test_each_dialog_replaces_the_previous_dialogs_handlers(self):
        addin.run(None)
        first = self.ui.open_command(addin.CMD_ID)
        second = self.ui.open_command(addin.CMD_ID)
        gc.collect()
        self.assertEqual(len(addin.dialog_handlers), 2)
        # Fusion holds handlers weakly: the first dialog's were released.
        self.assertEqual(len(first.inputChanged.handlers), 0)
        self.assertEqual(len(second.inputChanged.handlers), 1)

    def test_exceptions_never_escape_event_handlers(self):
        addin.run(None)
        command = self.ui.open_command(addin.CMD_ID)
        with mock.patch.object(push_dialog.PushDialog, "on_input_changed", side_effect=RuntimeError("boom")):
            adsk.core.change_input(command, "commitMsgPush", value="x")  # must not raise
        with mock.patch.object(push_dialog.PushDialog, "_execute", side_effect=RuntimeError("boom")):
            args = adsk.core.press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("ExecuteHandler failed", self.last_message())

    def test_dialog_creation_failure_is_reported_not_raised(self):
        addin.run(None)
        with mock.patch.object(push_dialog.PushDialog, "build", side_effect=RuntimeError("broken")):
            self.ui.open_command(addin.CMD_ID)
        self.assertIn("GitCommandCreatedEventHandler failed", self.last_message())

    def test_log_file_is_written_and_secrets_are_redacted(self):
        addin.run(None)
        addin.logger.info("pushing to https://user:ghp_%s@github.com/x", "A" * 36)
        import addin_logging

        with open(addin_logging.log_file_path(), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Logger initialized", text)
        self.assertNotIn("ghp_", text)


if __name__ == "__main__":
    unittest.main()
