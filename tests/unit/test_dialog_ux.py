"""S5 dialog behaviour through the SIMULATED Fusion API: validation, history modes, links, setup check.

What real Fusion shows (layout, OK button state, icons) is checked by the
consolidated acceptance matrix; see tests/fakes/README.md assumptions 27-32.
"""

import unittest
from unittest import mock

import _paths  # noqa: F401
from addin_harness import AddinTestCase, DialogResults
from adsk.core import change_input, click, ok_enabled

import fusion_git_core as core
import setup_check
from fusion_bridge import LINK_QUESTION

YES, NO, CANCEL = DialogResults.DialogYes, DialogResults.DialogNo, DialogResults.DialogCancel


def item(command, input_id):
    return command.commandInputs.itemById(input_id)


class Base(AddinTestCase):
    def single_profile(self, **extra):
        profile = self.work_profile(historyMode="single", exportSubfolder="designs",
                                    defaultMessage="{filename}: {message}", publicationNoticeAccepted=True)
        profile.update(extra)
        return profile

    def history(self, ref, path):
        return core.git_run(self.origin, "show", f"{ref}:{path}").stdout


class ValidationTests(Base):
    def test_ok_is_disabled_until_what_changed_is_filled_in(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.assertEqual(item(command, "commitMsgPush").value, "")
        self.assertFalse(ok_enabled(command))
        self.assertIn("Describe what changed", item(command, "validationSummary").text)
        change_input(command, "commitMsgPush", value="holes 5 mm")
        self.assertTrue(ok_enabled(command))
        self.assertEqual(item(command, "validationSummary").text, "")
        change_input(command, "commitMsgPush", value="   ")
        self.assertFalse(ok_enabled(command))

    def test_no_file_type_and_bad_branch_names_disable_ok(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        change_input(command, "commitMsgPush", value="x")
        for fmt_item in item(command, "exportFormatsConfig").listItems:
            fmt_item.isSelected = False
        change_input(command, "exportFormatsConfig")
        self.assertFalse(ok_enabled(command))
        self.assertIn("at least one file", item(command, "validationSummary").text)
        list(item(command, "exportFormatsConfig").listItems)[0].isSelected = True
        change_input(command, "exportFormatsConfig")
        change_input(command, "targetBranch", value="my backups")
        self.assertFalse(ok_enabled(command))
        self.assertIn("Backup branch", item(command, "validationSummary").text)
        change_input(command, "targetBranch", value="fusion-backups")
        self.assertTrue(ok_enabled(command))

    def test_setup_needs_an_address(self):
        self.design()
        command = self.open_dialog()
        change_input(command, "commitMsgPush", value="first")
        self.assertFalse(ok_enabled(command))
        self.assertIn("Paste the GitHub address", item(command, "validationSummary").text)

    def test_the_message_is_never_prefilled(self):
        self.seed({"Designs": self.single_profile()},
                  meta={"lastSelectedRepo": "Designs", "lastCommitMessage": "old note"})
        command = self.open_dialog()
        self.assertEqual(item(command, "commitMsgPush").value, "")


class HistoryModeTests(Base):
    def test_one_running_history_on_main_for_new_style_profiles(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design("Bracket")
        for note in ("first version", "holes widened at {timestamp}"):
            command = self.open_dialog()
            self.assertFalse(item(command, "snapshotMode").value)
            self.assertFalse(item(command, "branchPreview").isVisible)
            self.assertIn("the repository's main branch › designs/Bracket/", item(command, "destinationText").text)
            self.assertFalse(self.push(command, message=note).executeFailed, self.ui.texts())
        self.assertEqual(self.remote_branches(), ["main"])
        self.assertEqual(self.remote_files("main"),
                         [".gitattributes", "designs/Bracket/Bracket.step", "designs/Bracket/HISTORY.md"])
        log = core.git_run(self.origin, "log", "--format=%s", "main").stdout.splitlines()
        self.assertEqual(log[:2], ["Bracket: holes widened at {timestamp}", "Bracket: first version"])
        history = self.history("main", "designs/Bracket/HISTORY.md")
        self.assertEqual(history.count("## "), 2)
        self.assertIn("- **Fusion version:** v1", history)
        self.assertIn("<!-- fusion-to-github design: ", history)
        self.assertNotIn("urn:adsk", history)  # only a hash of the design's id is published
        self.assertIn("Saved to: main › designs/Bracket/", self.last_message())

    def test_a_backup_branch_of_its_own(self):
        self.seed({"Designs": self.single_profile(targetBranch="fusion-backups")}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.assertEqual(item(command, "targetBranch").value, "fusion-backups")
        self.assertIn("fusion-backups › designs/Bracket/", item(command, "destinationText").text)
        self.assertFalse(self.push(command).executeFailed, self.ui.texts())
        self.assertEqual(sorted(self.remote_branches()), ["fusion-backups", "main"])
        self.assertIn("designs/Bracket/Bracket.step", self.remote_files("fusion-backups"))
        self.assertNotIn("designs/Bracket/Bracket.step", self.remote_files("main"))

    def test_profiles_from_before_0_7_keep_their_snapshot_branches(self):
        self.seed({"Designs": self.work_profile(publicationNoticeAccepted=True)}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.assertTrue(item(command, "snapshotMode").value)
        self.assertTrue(item(command, "branchPreview").isVisible)
        self.assertFalse(item(command, "targetBranch").isVisible)
        self.assertIn("a new branch for each backup", item(command, "destinationText").text)
        self.assertFalse(self.push(command).executeFailed)
        self.assertTrue(any(b.startswith("fusion-export/") for b in self.remote_branches()))
        self.assertNotIn("historyMode", {k for k, v in self.profile("Designs").items() if v == "single"})
        self.assertEqual(self.profile("Designs")["historyMode"], "snapshot")

    def test_switching_to_separate_branches_is_saved(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        change_input(command, "snapshotMode", value=True)
        self.assertTrue(item(command, "branchFormatConfig").isVisible)
        self.assertFalse(item(command, "targetBranch").isVisible)
        self.assertFalse(self.push(command).executeFailed)
        self.assertEqual(self.profile("Designs")["historyMode"], "snapshot")
        self.assertTrue(any(b.startswith("fusion-export/") for b in self.remote_branches()))

    def test_unsaved_changes_are_shown_and_recorded(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design().parentDocument.isModified = True
        command = self.open_dialog()
        self.assertIn("v1 with unsaved changes", item(command, "designStatus").text)
        self.assertIn("doesn't until you save", item(command, "designStatus").text)
        self.push(command)
        self.assertIn("- **Fusion version:** v1 with unsaved changes",
                      self.history("main", "designs/Bracket/HISTORY.md"))


class LinkTests(Base):
    LINK = "https://github.com/acme/designs/tree/main/designs/Bracket"

    def setUp(self):
        super().setUp()
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()

    def test_yes_opens_the_design_folder_on_github(self):
        command = self.open_dialog()
        self.answer(YES)
        self.push(command)
        self.assertIn(LINK_QUESTION, self.ui.questions[-1])
        self.opened_urls.assert_called_once_with(self.LINK)

    def test_no_copies_the_link(self):
        command = self.open_dialog()
        self.answer(NO)
        self.push(command)
        self.assertEqual(self.copied, [self.LINK])
        self.assertIn("The link is on the clipboard", self.last_message())
        self.opened_urls.assert_not_called()

    def test_a_failed_copy_shows_the_link_to_copy_by_hand(self):
        command = self.open_dialog()
        self.answer(NO)
        with mock.patch("github_links.copy_to_clipboard", return_value=False):
            self.push(command)
        self.assertEqual(self.ui.input_prompts[-1].split(" (")[0], "Copy this link")

    def test_no_link_question_without_a_web_address(self):
        self.seed({"Local": self.single_profile(url="")}, meta={"lastSelectedRepo": "Local"})
        command = self.open_dialog()
        self.push(command)
        self.assertNotIn(LINK_QUESTION, self.last_message())
        self.assertIn("Backed up", self.last_message())


class CheckMySetupTests(Base):
    def test_a_saved_repository_is_checked_including_the_connection(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        click(command, "checkSetup")
        self.wait_for_push()
        report = self.last_message()
        self.assertTrue(report.startswith("Check My Setup"), report)
        self.assertIn("[OK] Git ", report)
        self.assertIn("[OK] The local folder for 'Designs' is ready.", report)
        self.assertIn("GitHub accepted the sign-in. The repository is empty.", report)
        self.assertEqual(self.remote_branches(), [])  # nothing was pushed or changed

    def test_a_connection_failure_is_explained(self):
        core.git_run(self.work, "remote", "set-url", "origin", self.base + "/missing.git")
        self.seed({"Designs": self.single_profile(url="")}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        click(command, "checkSetup")
        self.wait_for_push()
        self.assertIn("[Problem] GitHub couldn't find the repository", self.last_message())

    def test_setup_is_checked_locally_before_a_repository_exists(self):
        command = self.open_dialog()
        click(command, "checkSetup")
        report = self.last_message()
        self.assertIn("[OK] Git ", report)
        self.assertIn("The connection to GitHub wasn't tested.", report)

    def test_first_run_reports_a_missing_git_at_once(self):
        missing = setup_check.Check(setup_check.PROBLEM, "Git was not found on this computer.")
        with mock.patch.object(setup_check, "check_git", return_value=missing):
            self.open_dialog()
        self.assertIn("Before your first backup", self.last_message())
        self.assertIn("[Problem] Git was not found", self.last_message())

    def test_no_first_run_report_for_returning_users(self):
        self.seed({"Designs": self.single_profile()}, meta={"lastSelectedRepo": "Designs"})
        missing = setup_check.Check(setup_check.PROBLEM, "Git was not found on this computer.")
        with mock.patch.object(setup_check, "check_git", return_value=missing):
            self.open_dialog()
        self.assertEqual(self.ui.messages, [])


class DesignFolderOwnershipTests(Base):
    """Risk R-24: two saved repositories for one GitHub repository."""

    def test_two_profiles_never_share_a_folder_between_different_designs(self):
        self.seed({"A": self.single_profile(), "B": self.single_profile()}, meta={"lastSelectedRepo": "A"})
        self.design("Bracket", "urn:adsk:first-bracket")
        self.push(self.open_dialog())
        # Through B, a *different* design that is also called Bracket.
        self.seed({}, meta={"lastSelectedRepo": "B"})
        self.design("Bracket", "urn:adsk:second-bracket")
        self.push(self.open_dialog())
        files = self.remote_files("main")
        self.assertIn("designs/Bracket/Bracket.step", files)
        self.assertIn("designs/Bracket (2)/Bracket.step", files)
        self.assertEqual(self.profile("B")["designs"]["urn:adsk:second-bracket"]["folder"], "Bracket (2)")
        self.assertIn("this design's folder is 'Bracket (2)'", self.last_message())
        first = self.history("main", "designs/Bracket/HISTORY.md")
        second = self.history("main", "designs/Bracket (2)/HISTORY.md")
        self.assertEqual(first.count("## "), 1)
        self.assertEqual(second.count("## "), 1)
        # The first design pushed through B finds its own folder again.
        self.design("Bracket", "urn:adsk:first-bracket")
        self.push(self.open_dialog())
        self.assertEqual(self.history("main", "designs/Bracket/HISTORY.md").count("## "), 2)
        self.assertEqual(self.profile("B")["designs"]["urn:adsk:first-bracket"]["folder"], "Bracket")

    def seed(self, repositories, meta=None):
        if repositories:
            return super().seed(repositories, meta)
        # Only change the last selected repository.
        from settings_store import SettingsStore

        store = SettingsStore(self.settings_path)
        store.load()
        store.meta.update(meta or {})
        store.save()


if __name__ == "__main__":
    unittest.main()
