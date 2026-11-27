"""Exports through the "Push to GitHub" dialog, driven by the SIMULATED Fusion API.

What is checked is what the user sees and what reaches the (local, bare)
"GitHub" remote: a failed export pushes nothing at all, linked components
are asked about and recorded, STL settings are saved with the profile.
"""

import unittest

import _paths  # noqa: F401
import adsk.fusion
from addin_harness import AddinTestCase, DialogResults
from adsk.core import press_ok, select_item

import fusion_git_core as core

YES, NO = DialogResults.DialogYes, DialogResults.DialogNo


def item(command, input_id):
    return command.commandInputs.itemById(input_id)


class DialogExportCase(AddinTestCase):
    def remote_refs(self):
        return core.git_run(self.origin, "for-each-ref", "--format=%(refname) %(objectname)").stdout

    def push(self, expect_ok=True):
        command = self.open_dialog()
        args = press_ok(command)
        self.assertEqual(args.executeFailed, not expect_ok, self.ui.texts())
        return command

    def pushed_branch(self):
        return sorted(b for b in self.remote_branches() if b.startswith("fusion-export/"))[-1]

    def history(self, branch, design="Bracket"):
        return core.git_run(self.origin, "show", f"{branch}:{design}/HISTORY.md").stdout


class FailedExportTests(DialogExportCase):
    def test_any_failed_export_pushes_nothing_and_leaves_history_alone(self):
        self.seed({"Designs": self.work_profile(exportFormats=["f3d", "step", "stl"])},
                  meta={"lastSelectedRepo": "Designs"})
        self.design()
        self.answer(YES)  # the one-time publication notice
        self.push()
        before = self.remote_refs()
        history_before = self.history(self.pushed_branch())
        for mode in ("raise", "false", "empty", "missing", "corrupt"):
            with self.subTest(mode=mode):
                self.design().exportManager.failures = {"stl": mode}
                self.push(expect_ok=False)
                message = self.last_message()
                self.assertIn("Nothing was pushed because these exports failed:", message)
                self.assertIn("Bracket.stl", message)
                self.assertEqual(self.remote_refs(), before)
        self.assertEqual(self.history(self.pushed_branch()), history_before)


class LinkedComponentDialogTests(DialogExportCase):
    def setUp(self):
        super().setUp()
        self.seed({"Designs": self.work_profile(exportFormats=["f3d", "step"])},
                  meta={"lastSelectedRepo": "Designs"})
        design = self.design()
        design.rootComponent.add_occurrence(adsk.fusion.Component("Bolt M5"), linked=True)

    def test_declining_cancels_and_keeps_the_dialog_open(self):
        self.answer(NO)
        self.push(expect_ok=False)
        self.assertIn("uses 1 linked component (Bolt M5)", self.ui.questions[0])
        self.assertIn("Push cancelled", self.last_message())
        self.assertEqual(self.remote_branches(), [])

    def test_accepting_pushes_and_records_a_history_note(self):
        self.answer(YES, YES)  # linked components, then the publication notice
        self.push()
        history = self.history(self.pushed_branch())
        self.assertIn(
            "- **Note:** Contains 1 linked component (Bolt M5); this .f3d backup may not be self-contained.",
            history,
        )


class StlSettingTests(DialogExportCase):
    def test_one_file_per_body_is_saved_and_pushed(self):
        self.seed({"Designs": self.work_profile(exportFormats=["stl"])}, meta={"lastSelectedRepo": "Designs"})
        self.app.activeProduct = adsk.fusion.Design("Bracket", "urn:adsk:bracket", bodies=("Arm", "arm"))
        command = self.open_dialog()
        files = next(i for i in item(command, "formatSettingsTable").cells.values()
                     if i.id.startswith("formatSetting_stl_files"))
        select_item(command, files.id, "One file per body")
        self.answer(YES)  # the one-time publication notice
        self.assertFalse(press_ok(command).executeFailed, self.ui.texts())
        self.assertEqual(self.profile("Designs")["formatSettings"]["stl"],
                         {"meshRefinement": "high", "files": "perBody"})
        self.assertEqual(self.remote_files(self.pushed_branch()), [
            ".gitattributes", "Bracket/Bracket - Arm.stl", "Bracket/Bracket - arm (2).stl", "Bracket/HISTORY.md",
        ])

    def test_a_profile_saved_before_the_files_setting_pushes_one_stl(self):
        profile = self.work_profile(exportFormats=["stl"], formatSettings={"stl": {"meshRefinement": "medium"}})
        self.seed({"Designs": profile}, meta={"lastSelectedRepo": "Designs"})
        self.app.activeProduct = adsk.fusion.Design("Bracket", "urn:adsk:bracket", bodies=("Arm", "Leg"))
        command = self.open_dialog()
        selected = {cell.id.rsplit("_g", 1)[0]: cell.selectedItem.name
                    for cell in item(command, "formatSettingsTable").cells.values() if hasattr(cell, "selectedItem")}
        self.assertEqual(selected, {"formatSetting_stl_meshRefinement": "Medium", "formatSetting_stl_files": "One file"})
        self.answer(YES)
        self.assertFalse(press_ok(command).executeFailed, self.ui.texts())
        self.assertEqual(self.remote_files(self.pushed_branch()),
                         [".gitattributes", "Bracket/Bracket.stl", "Bracket/HISTORY.md"])

    def test_old_fusion_without_stl_units_warns_in_the_summary(self):
        self.seed({"Designs": self.work_profile(exportFormats=["stl"])}, meta={"lastSelectedRepo": "Designs"})
        self.design().exportManager.stl_unit_type_supported = False
        self.answer(YES)
        self.push()
        self.assertIn("STL files have no units", self.last_message())


if __name__ == "__main__":
    unittest.main()
