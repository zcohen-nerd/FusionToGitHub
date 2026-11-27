"""Add-in start/stop and handler lifetime, against the SIMULATED Fusion API."""

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
        definition = self.ui.commandDefinitions.addButtonDefinition(addin.CMD_ID, addin.CMD_NAME, "", "")
        self.ui.allToolbarPanels.item(0).controls.addCommand(definition, addin.CONTROL_ID)
        addin.run(None)
        self.assertEqual(len(self.controls()), 1)

    def test_stop_removes_button_definition_and_all_handlers(self):
        addin.run(None)
        self.ui.open_command(addin.CMD_ID)
        self.assertEqual(len(addin.dialog_handlers), 2)
        addin.stop(None)
        self.assertEqual(self.controls(), [])
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
        self.ui.open_command(addin.CMD_ID)
        self.assertEqual(len(addin.dialog_handlers), 2)
        self.assertEqual(len(first.inputChanged.handlers), 1)

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
