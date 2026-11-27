"""The "Push to GitHub" dialog, driven through the SIMULATED Fusion API.

Behaviour is checked through what a user would see and what ends up on disk
or on the (local, bare) "GitHub" remote — not through internal calls. Pushes
run in the background; ``self.push(command)`` presses OK and waits for them.
"""

import json
import os
import unittest
from pathlib import Path

import _paths  # noqa: F401
from addin_harness import AddinTestCase, DialogResults
from adsk.core import change_input, click, press_ok, select_item

import fusion_git_core as core
from push_dialog import ADD_NEW_OPTION

YES, NO, CANCEL = DialogResults.DialogYes, DialogResults.DialogNo, DialogResults.DialogCancel


def item(command, input_id):
    return command.commandInputs.itemById(input_id)


def selected(command, input_id):
    return [i.name for i in item(command, input_id).listItems if i.isSelected]


class OpeningTests(AddinTestCase):
    def test_lists_saved_repositories_and_selects_the_last_used(self):
        self.seed(
            {"Zeta": self.work_profile(), "Alpha": self.work_profile(exportFormats=["stl", "sat"])},
            meta={"lastSelectedRepo": "Alpha", "lastCommitMessage": "previous note"},
        )
        command = self.open_dialog()
        names = [i.name for i in item(command, "repoSelector").listItems]
        self.assertEqual(names, [ADD_NEW_OPTION, "Alpha", "Zeta"])
        self.assertEqual(selected(command, "repoSelector"), ["Alpha"])
        self.assertEqual(sorted(selected(command, "exportFormatsConfig")), ["sat", "stl"])
        self.assertEqual(item(command, "commitMsgPush").value, "previous note")
        self.assertFalse(item(command, "gitUrl").isVisible)  # saved repo: setup fields hidden
        self.assertTrue(item(command, "editRepo").isVisible)
        self.assertEqual(self.ui.messages, [])  # nothing unusual to report

    def test_new_users_start_on_setup(self):
        command = self.open_dialog()
        self.assertEqual(selected(command, "repoSelector"), [ADD_NEW_OPTION])
        self.assertTrue(item(command, "gitUrl").isVisible)
        self.assertFalse(item(command, "editRepo").isVisible)
        self.assertEqual(item(command, "repoPath").value, os.path.join(self.repos_dir, "NewRepo"))

    def test_unreadable_settings_are_reported_once_and_kept(self):
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        self.open_dialog()
        reports = [t for t in self.ui.texts() if "couldn't be read" in t]
        self.assertEqual(len(reports), 1)
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{broken")
        self.assertTrue(any(n.startswith("settings.json.corrupt-") for n in os.listdir(self.base)))


class SelectionAndValidationTests(AddinTestCase):
    def test_switching_repositories_applies_their_settings_and_clears_token_entry(self):
        self.seed({
            "A": self.work_profile(defaultMessage="A note", exportSubfolder="cad"),
            "B": self.work_profile(defaultMessage="B note", branchFormat="b/{filename}", useStoredPat=True),
        }, meta={"lastSelectedRepo": "A"})
        command = self.open_dialog()
        self.assertEqual(item(command, "exportSubfolder").value, "cad")
        self.answer(YES)  # no token yet → "Add one now?"
        click(command, "managePat")
        self.assertTrue(item(command, "patToken").isVisible)
        item(command, "patToken").value = "half-typed"
        select_item(command, "repoSelector", "B")
        self.assertEqual(item(command, "defaultMessageConfig").value, "B note")
        self.assertEqual(item(command, "branchFormatConfig").value, "b/{filename}")
        self.assertEqual(item(command, "exportSubfolder").value, "")
        self.assertTrue(item(command, "useStoredPat").value)
        self.assertFalse(item(command, "patToken").isVisible)
        self.assertEqual(item(command, "patToken").value, "")

    def test_new_repository_validation_messages(self):
        command = self.open_dialog()
        change_input(command, "gitUrl", value="github.com/acme/widgets")
        self.assertIn("https://github.com/acme/widgets.git", item(command, "conversionStatus").text)
        self.assertIn("Repository name: widgets", item(command, "conversionStatus").text)
        self.assertIn("valid", item(command, "gitValidationStatus").text)
        change_input(command, "gitUrl", value="not a url")
        self.assertIn("❌", item(command, "gitValidationStatus").text)

    def test_a_url_with_a_token_is_refused(self):
        command = self.open_dialog()
        change_input(command, "gitUrl", value="https://me:ghp_" + "x" * 36 + "@github.com/acme/widgets.git")
        self.assertIn("token", item(command, "gitValidationStatus").text)
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("Please fix these issues", self.last_message())
        self.assertFalse(os.path.exists(self.repos_dir))

    def test_changing_formats_rebuilds_the_settings_table_without_id_clashes(self):
        command = self.open_dialog()
        formats = item(command, "exportFormatsConfig")
        for fmt_item in formats.listItems:
            fmt_item.isSelected = fmt_item.name in ("step", "stl")
        change_input(command, "exportFormatsConfig")
        change_input(command, "exportFormatsConfig")  # a second rebuild must not collide
        table = item(command, "formatSettingsTable")
        self.assertEqual(table.rowCount, 3)  # header + step + stl
        labels = sorted(cell.text for (row, col), cell in table.cells.items() if col == 0 and row > 0)
        self.assertEqual(labels, ["STEP", "STL"])

    def test_format_setting_choice_is_saved_with_the_push(self):
        self.seed({"Designs": self.work_profile(exportFormats=["stl"])}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        stl_dropdown = next(i for i in item(command, "formatSettingsTable").cells.values() if i.id.startswith("formatSetting_stl"))
        select_item(command, stl_dropdown.id, "Low (fast)")
        self.answer(YES)  # the one-time publication notice
        self.assertFalse(self.push(command).executeFailed, self.ui.texts())
        self.assertEqual(self.profile("Designs")["formatSettings"], {"stl": {"meshRefinement": "low"}})


class TokenTests(AddinTestCase):
    def setUp(self):
        super().setUp()
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})

    def test_token_entry_is_masked_saved_and_cleared(self):
        command = self.open_dialog()
        self.answer(YES)  # "No stored token… Add one now?"
        click(command, "managePat")
        token_input = item(command, "patToken")
        self.assertTrue(token_input.isVisible)
        self.assertTrue(token_input.isPassword)
        token_input.value = "ghp_" + "t" * 36
        item(command, "patUsername").value = "octocat"
        click(command, "patSave")
        # Bound to the repository's server (here from its saved address,
        # because the sandbox remote is a local folder).
        self.assertEqual(self.creds.get("Designs"),
                         {"username": "octocat", "token": "ghp_" + "t" * 36, "host": "github.com"})
        self.assertIn("for github.com", self.last_message())
        self.assertEqual(token_input.value, "")
        self.assertFalse(token_input.isVisible)
        self.assertTrue(item(command, "useStoredPat").value)
        self.assertNotIn("ghp_", "\n".join(self.ui.texts()))

    def test_empty_token_is_not_saved(self):
        command = self.open_dialog()
        self.answer(YES)  # "Add one now?"
        click(command, "managePat")
        click(command, "patSave")
        self.assertIsNone(self.creds.get("Designs"))
        self.assertIn("Paste a token", self.last_message())

    def test_existing_token_can_be_deleted(self):
        self.creds.set("Designs", "", "ghp_" + "d" * 36)
        command = self.open_dialog()
        self.answer(NO)  # Yes: replace / No: delete / Cancel
        click(command, "managePat")
        self.assertIsNone(self.creds.get("Designs"))
        self.assertIn("revoke", self.last_message())

    def test_use_stored_token_needs_a_token(self):
        command = self.open_dialog()
        change_input(command, "useStoredPat", value=True)
        self.assertFalse(item(command, "useStoredPat").value)


class EditRemoveTests(AddinTestCase):
    def setUp(self):
        super().setUp()
        self.seed({"Designs": self.work_profile(useStoredPat=True)}, meta={"lastSelectedRepo": "Designs"})
        self.creds.set("Designs", "", "ghp_" + "e" * 36)

    def test_edit_shows_current_values_and_pressing_again_cancels(self):
        command = self.open_dialog()
        click(command, "editRepo")
        self.assertTrue(item(command, "saveRepoEdit").isVisible)
        self.assertEqual(item(command, "editRepoName").value, "Designs")
        self.assertEqual(item(command, "editGitUrl").value, "https://github.com/acme/designs.git")
        click(command, "editRepo")
        self.assertFalse(item(command, "saveRepoEdit").isVisible)

    def test_rename_moves_the_token_and_refreshes_the_list(self):
        command = self.open_dialog()
        click(command, "editRepo")
        item(command, "editRepoName").value = "Parts"
        click(command, "saveRepoEdit")
        self.assertEqual(selected(command, "repoSelector"), ["Parts"])
        self.assertIsNone(self.profile("Designs"))
        self.assertIsNotNone(self.profile("Parts"))
        self.assertIsNone(self.creds.get("Designs"))
        self.assertIsNotNone(self.creds.get("Parts"))

    def test_moving_to_another_server_turns_off_the_stored_token(self):
        command = self.open_dialog()
        click(command, "editRepo")
        item(command, "editGitUrl").value = "https://gitlab.example.invalid/acme/designs.git"
        origin_before = core.git_run(self.work, "remote", "get-url", "origin").stdout
        self.answer(NO)  # don't repoint the local folder
        click(command, "saveRepoEdit")
        self.assertFalse(self.profile("Designs")["useStoredPat"])
        self.assertFalse(item(command, "useStoredPat").value)
        self.assertEqual(core.git_run(self.work, "remote", "get-url", "origin").stdout, origin_before)
        self.assertIn("Use Stored Token", self.last_message())

    def test_invalid_edit_changes_nothing(self):
        command = self.open_dialog()
        click(command, "editRepo")
        item(command, "editRepoPath").value = os.path.join(self.base, "not-a-repo")
        click(command, "saveRepoEdit")
        self.assertIn("not changed", self.last_message())
        self.assertEqual(self.profile("Designs")["path"], self.work)

    def test_remove_forgets_the_entry_but_keeps_folder_and_token(self):
        command = self.open_dialog()
        self.answer(YES, NO)  # remove? yes — also delete token? no
        click(command, "removeRepo")
        self.assertIsNone(self.profile("Designs"))
        self.assertEqual(selected(command, "repoSelector"), [ADD_NEW_OPTION])
        self.assertTrue(os.path.isdir(os.path.join(self.work, ".git")))
        self.assertIsNotNone(self.creds.get("Designs"))
        self.assertIn("not touched", self.ui.questions[0])

    def test_remove_can_also_delete_the_token_when_asked_separately(self):
        command = self.open_dialog()
        self.answer(YES, YES)
        click(command, "removeRepo")
        self.assertIsNone(self.creds.get("Designs"))

    def test_declining_remove_changes_nothing(self):
        command = self.open_dialog()
        self.answer(NO)
        click(command, "removeRepo")
        self.assertIsNotNone(self.profile("Designs"))


class PushTests(AddinTestCase):
    def test_successful_push_lands_in_the_design_folder(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design("Bracket")
        command = self.open_dialog()
        item(command, "commitMsgPush").value = "holes 5mm"
        self.answer(YES)  # the one-time publication notice
        args = self.push(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        self.assertTrue(command.isTerminated)  # the dialog closed when the push started
        success = self.last_message()
        self.assertIn("Pushed to GitHub, branch: fusion-export/Bracket-", success)
        self.assertIn("Bracket/Bracket.step", success)
        branch = next(b for b in self.remote_branches() if b.startswith("fusion-export/"))
        self.assertEqual(self.remote_files(branch), [".gitattributes", "Bracket/Bracket.step", "Bracket/HISTORY.md"])
        self.assertIn("holes 5mm", core.git_run(self.origin, "log", "-1", "--format=%s", branch).stdout)
        self.assertTrue(self.profile("Designs")["publicationNoticeAccepted"])
        self.assertEqual(self.settings()["meta"]["lastCommitMessage"], "holes 5mm")
        self.assertTrue(any("publishes your design" in q or "pushes your design" in q for q in self.ui.questions))

    def test_declining_the_publication_notice_keeps_the_dialog_open(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.answer(NO)
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("Push cancelled", self.last_message())
        self.assertEqual(self.remote_branches(), [])

    def test_identity_prompt_is_saved_for_the_repository_only(self):
        profile = self.work_profile()
        del profile["gitIdentity"]
        self.seed({"Designs": profile}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.ui.input_answers.extend([("Ada Lovelace", False), ("ada@example.invalid", False)])
        self.answer(YES, NO)  # publication notice: yes; use for all repositories: no
        global_before = Path(self.global_config).read_bytes()
        args = self.push(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        self.assertEqual(self.profile("Designs")["gitIdentity"], {"name": "Ada Lovelace", "email": "ada@example.invalid"})
        self.assertEqual(Path(self.global_config).read_bytes(), global_before)
        branch = self.remote_branches()[-1]
        self.assertEqual(core.git_run(self.origin, "log", "-1", "--format=%ae", branch).stdout.strip(), "ada@example.invalid")

    def test_cancelling_the_identity_prompt_pushes_nothing(self):
        profile = self.work_profile()
        del profile["gitIdentity"]
        self.seed({"Designs": profile}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.answer(YES)  # the one-time publication notice
        args = press_ok(command)  # inputBox queue empty → cancelled
        self.assertTrue(args.executeFailed)
        self.assertEqual(self.remote_branches(), [])
        self.assertNotIn("gitIdentity", self.profile("Designs"))

    def test_missing_stored_token_is_refused_before_pushing(self):
        self.seed({"Designs": self.work_profile(useStoredPat=True)}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.answer(YES)  # the one-time publication notice
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("No stored token", self.last_message())
        self.assertEqual(self.remote_branches(), [])

    def test_git_failure_is_reported_after_the_dialog_closed(self):
        # Git runs in the background, after the dialog has closed (S4, Q6).
        core.git_run(self.work, "remote", "set-url", "origin", os.path.join(self.base, "missing.git"))
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.answer(YES)  # the one-time publication notice
        args = self.push(command)
        self.assertFalse(args.executeFailed)
        self.assertTrue(any(t.startswith("Push failed") for t in self.ui.texts()), self.ui.texts())
        self.assertIn("Git operations failed", self.last_message())

    def test_no_design_open(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("No active Fusion design", self.last_message())

    def test_failed_export_is_reported_and_nothing_is_pushed(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        self.design().exportManager.fail_formats = {"step"}
        command = self.open_dialog()
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertIn("No files exported", self.last_message())
        self.assertEqual(self.remote_branches(), [])

    def test_blank_name_setup_pushes_from_the_folder_it_cloned_into(self):
        """BUG-01: set up from a URL with the name left blank, then push."""
        url = "https://github.com/acme/MyDesigns.git"
        # Route that GitHub address to the local bare repository, in the
        # isolated global config only.
        core.git_run(self.base, "config", "--global", f"url.{Path(self.origin).as_uri()}.insteadOf", url)
        self.design()
        command = self.open_dialog()
        change_input(command, "gitUrl", value="github.com/acme/MyDesigns")
        self.ui.input_answers.extend([("Ada", False), ("ada@example.invalid", False)])
        self.answer(YES, NO)
        args = self.push(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        clone = os.path.join(self.repos_dir, "MyDesigns")
        self.assertEqual(self.profile("MyDesigns")["path"], clone)
        self.assertTrue(os.path.isdir(os.path.join(clone, ".git")))
        self.assertFalse(os.path.exists(os.path.join(self.repos_dir, "NewRepo")))
        self.assertTrue(any(b.startswith("fusion-export/") for b in self.remote_branches()))


class LogAndPrivacyTests(AddinTestCase):
    def test_clear_log_and_privacy_link(self):
        command = self.open_dialog()
        self.answer(YES)
        click(command, "clearLogFile")
        self.assertIn("Log cleared", self.last_message())
        click(command, "openPrivacy")
        self.opened_urls.assert_called_once()
        self.assertIn("PRIVACY.md", self.opened_urls.call_args[0][0])

    def test_log_level_choice(self):
        import addin_logging

        command = self.open_dialog()
        select_item(command, "logLevel", "DEBUG")
        self.assertEqual(addin_logging.current_log_level_name, "DEBUG")
        select_item(command, "logLevel", "INFO")


class ReviewFixDialogTests(AddinTestCase):
    """Regressions for the S3 independent review findings."""

    TOKEN = "ghp_" + "w" * 36

    def test_token_entry_closes_when_switching_to_setup(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        self.answer(YES)  # "Add one now?"
        click(command, "managePat")
        item(command, "patToken").value = self.TOKEN
        select_item(command, "repoSelector", ADD_NEW_OPTION)
        self.assertFalse(item(command, "patToken").isVisible)
        self.assertEqual(item(command, "patToken").value, "")

    def test_remove_clears_the_setup_form(self):
        self.seed({"Designs": self.work_profile()}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        self.answer(YES)  # remove? (no stored token, so no second question)
        click(command, "removeRepo")
        self.assertEqual(selected(command, "repoSelector"), [ADD_NEW_OPTION])
        self.assertEqual(item(command, "gitUrl").value, "")
        self.assertEqual(item(command, "newRepoName").value, "")

    def test_edit_keeps_choices_not_yet_pushed(self):
        self.seed({"Designs": self.work_profile(defaultMessage="saved note")}, meta={"lastSelectedRepo": "Designs"})
        command = self.open_dialog()
        item(command, "defaultMessageConfig").value = "unsaved note"
        click(command, "editRepo")
        item(command, "editRepoName").value = "Renamed"
        click(command, "saveRepoEdit")
        self.assertEqual(selected(command, "repoSelector"), ["Renamed"])
        self.assertEqual(item(command, "defaultMessageConfig").value, "unsaved note")
        self.assertIn("Renamed", self.settings()["repositories"])

    def test_identity_for_all_repositories_only_when_chosen(self):
        profile = self.work_profile()
        del profile["gitIdentity"]
        self.seed({"Designs": profile}, meta={"lastSelectedRepo": "Designs"})
        self.design()
        command = self.open_dialog()
        self.ui.input_answers.extend([("Ada Lovelace", False), ("ada@example.invalid", False)])
        self.answer(YES, YES)  # publication notice; use for all repositories
        args = self.push(command)
        self.assertFalse(args.executeFailed, self.ui.texts())
        self.assertIn("ada@example.invalid", Path(self.global_config).read_text(encoding="utf-8"))
        self.assertEqual(self.profile("Designs")["gitIdentity"]["email"], "ada@example.invalid")

    def test_read_only_settings_are_never_overwritten(self):
        future = {"schemaVersion": 99, "meta": {"lastSelectedRepo": "Designs"},
                  "repositories": {"Designs": self.work_profile()}}
        Path(self.settings_path).write_text(json.dumps(future), encoding="utf-8")
        before = Path(self.settings_path).read_bytes()
        self.design()
        command = self.open_dialog()
        args = press_ok(command)
        self.assertTrue(args.executeFailed)
        self.assertEqual(Path(self.settings_path).read_bytes(), before)
        self.assertEqual(self.remote_branches(), [])

    def test_tracebacks_in_the_log_are_redacted(self):
        import logging

        import addin_logging

        formatter = addin_logging.RedactingFormatter("%(message)s")
        try:
            raise RuntimeError(f"fatal: https://bob:{self.TOKEN}@github.com/a/b.git")
        except RuntimeError:
            import sys

            record = logging.LogRecord("t", logging.ERROR, __file__, 1, "push failed", None, sys.exc_info())
        text = formatter.format(record)
        self.assertIn("push failed", text)
        self.assertIn("Traceback", text)
        self.assertNotIn(self.TOKEN, text)


if __name__ == "__main__":
    unittest.main()
