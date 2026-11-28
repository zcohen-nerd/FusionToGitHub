"""Regressions for the S7 pre-release reviews (correctness, security, test quality), with real Git."""

import base64
import os
import tempfile
import unittest
from unittest import mock

import _paths
from test_core_identity_history import GitSandbox, _UI

import fusion_git_core as core
from fusion_export import _safe_base
from push_controller import PushController
from settings_store import SettingsError, SettingsStore
from credentials import MemoryCredentialStore

TOKEN = "ghp_" + "r" * 36
# Before GitSandbox points it at a temporary folder.
REAL_CREDENTIALS_ROOT = core._credentials_root


class ConfirmingUI(_UI):
    def __init__(self, answer=True):
        super().__init__()
        self.questions, self.answer = [], answer

    def confirm(self, message):
        self.questions.append(message)
        return self.answer


class PushOutcomeTests(GitSandbox):
    def push(self, rel="designs/Bracket/Bracket.step", content="x", ui=None, **kwargs):
        ui = ui or ConfirmingUI()
        result = core.push_export(self.work, [(self.export(os.path.basename(rel), content), rel)], "note",
                                  "Bracket", ui, mode=core.MODE_SINGLE, identity=self.identity,
                                  history_file=None, **kwargs)
        return result, ui

    def tree(self):
        return core.git_run(self.origin, "ls-tree", "-r", "--name-only", "main").stdout.split()

    def test_a_cleanup_failure_after_the_push_is_not_reported_as_a_failed_push(self):
        real = core.git_run

        def flaky(repo, *args, **kwargs):
            if args[:2] == ("update-ref", "-d"):
                raise core.GitTimeoutError("git update-ref took longer than 60 seconds")
            return real(repo, *args, **kwargs)

        with mock.patch.object(core, "git_run", side_effect=flaky):
            result, ui = self.push()
        self.assertIsNotNone(result, ui.errors)
        self.assertEqual(ui.errors, [])
        self.assertIn("designs/Bracket/Bracket.step", self.tree())

    def test_a_design_renamed_only_in_case_updates_the_same_file(self):
        self.push("designs/Bracket/bracket.step", "one")
        result, _ = self.push("designs/Bracket/Bracket.step", "two")
        self.assertEqual(result["files"], ["designs/Bracket/bracket.step"])
        self.assertEqual([p for p in self.tree() if p.lower() == "designs/bracket/bracket.step"],
                         ["designs/Bracket/bracket.step"])
        self.assertEqual(core.git_run(self.origin, "show", "main:designs/Bracket/bracket.step").stdout, "two")

    def test_a_push_timeout_is_checked_on_github_before_reporting(self):
        real = core.git_run

        def slow_push(repo, *args, **kwargs):
            if args and args[0] == "push" and "refs/heads/main" in args[-1] and not args[-1].startswith(":"):
                real(repo, *args, **kwargs)  # it did reach GitHub...
                raise core.GitTimeoutError("git push took longer than 600 seconds")  # ...but the reply was lost
            return real(repo, *args, **kwargs)

        self.push("designs/Bracket/first.step")  # so the repository isn't empty
        with mock.patch.object(core, "git_run", side_effect=slow_push):
            result, ui = self.push("designs/Bracket/second.step")
        self.assertIsNotNone(result, ui.errors)  # confirmed on GitHub: reported as a success
        self.assertIn("designs/Bracket/second.step", self.tree())

    def test_a_push_timeout_that_did_not_arrive_is_reported_as_uncertain(self):
        real = core.git_run

        def lost_push(repo, *args, **kwargs):
            if args and args[0] == "push" and "refs/heads/main" in args[-1]:
                raise core.GitTimeoutError("git push took longer than 600 seconds")
            return real(repo, *args, **kwargs)

        self.push("designs/Bracket/first.step")
        with mock.patch.object(core, "git_run", side_effect=lost_push):
            result, ui = self.push("designs/Bracket/second.step")
        self.assertIsNone(result)
        self.assertIn("couldn't be confirmed whether this backup arrived", ui.errors[0])

    def test_declining_after_an_empty_repository_was_set_up_says_so(self):
        ui = ConfirmingUI(answer=False)
        result = core.push_export(self.work, [(self.export("a.step", "x"), "a.step")], "note", "Bracket", ui,
                                  mode=core.MODE_SNAPSHOT, branch_override="main", identity=self.identity,
                                  history_file=None)
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["repository_initialized"])
        self.assertIn("main", core.git_run(self.origin, "branch").stdout)

    def test_cancel_with_another_push_on_top_is_uncertain_not_nothing(self):
        state = {"phase": "pushing", "branch": "main", "commit": "1" * 40, "base": "2" * 40}
        with mock.patch.object(core, "git_output", return_value="3" * 40 + "\trefs/heads/main"):
            result = core._cancelled_result(self.work, state, None, None)
        self.assertTrue(result["uncertain"])
        self.assertFalse(result["published"])


class SecurityFixTests(GitSandbox):
    def auth(self):
        empty = tempfile.mkdtemp(prefix="ftg_nohooks_")
        self.addCleanup(_paths.force_rmtree, empty)
        return core.GitAuth(host="git.example.invalid", token=TOKEN, hooks_dir=empty)

    def test_repository_programs_and_background_maintenance_are_off_with_a_token(self):
        config = self.auth().config
        for item in ("core.alternateRefsCommand=true", "gc.auto=0", "maintenance.auto=false"):
            self.assertIn(item, config)

    def test_no_tls_verification_switch_is_inherited(self):
        with mock.patch.dict(os.environ, {"GIT_SSL_NO_VERIFY": "1"}):
            seen = core.git_run(self.work, "-c", "alias.showenv=!env", "showenv", auth=self.auth()).stdout
        self.assertNotIn("GIT_SSL_NO_VERIFY", seen)

    def test_redaction_and_address_checks(self):
        self.assertNotIn("ss", core.redact_secrets("fatal: https://u:p@ss@github.com/a/b").split("***")[0][-3:])
        self.assertEqual(core.redact_secrets("https://u:p@ss@github.com/a/b"), "https://***@github.com/a/b")
        self.assertTrue(core.url_has_embedded_secret("https://" + "a" * 40 + "@github.com/x/y"))
        self.assertFalse(core.url_has_embedded_secret("https://bob@github.com/x/y"))

    def test_object_ids_from_the_server_must_look_like_object_ids(self):
        listing = ("ref: refs/heads/main\tHEAD\n" + "a" * 40 + "\trefs/heads/main\n"
                   "--upload-pack=evil\trefs/heads/bad\n")
        with mock.patch.object(core, "git_output", return_value=listing):
            default, heads = core.remote_branches(self.work)
        self.assertEqual(heads, {"main": "a" * 40})

    def test_windows_credentials_never_fall_back_to_temp(self):
        home = os.path.join(self.base, "home")
        with mock.patch.object(core, "IS_WINDOWS", True), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": "", "USERPROFILE": home, "HOME": home}):
            root = REAL_CREDENTIALS_ROOT()
        self.assertEqual(root, os.path.join(home, ".PushToGitHub_AddIn_Data", "credentials"))
        self.assertNotEqual(root, tempfile.gettempdir())

    def test_the_token_reaches_neither_the_log_nor_the_settings_nor_git_config(self):
        # End to end through the controller: store a token, push with it (refused
        # here: the sandbox remote isn't https), and scan everything written.
        import logging

        log_path = os.path.join(self.base, "push.log")
        logger = logging.getLogger("ftg-token-scan")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (logger.removeHandler(handler), handler.close()))
        settings = os.path.join(self.base, "settings.json")
        store = SettingsStore(settings)
        store.load()
        store.add("R", {"path": self.work, "url": "https://git.example.invalid/acme/designs.git", "useStoredPat": True})
        store.save()
        creds = MemoryCredentialStore()
        controller = PushController(store, creds, logger)
        core.git_run(self.work, "remote", "set-url", "origin", "https://git.example.invalid/acme/designs.git")
        controller.store_token("R", "octocat", TOKEN)
        token_form = core.token_secrets(TOKEN, "octocat")[1]
        try:
            from push_controller import PushRequest
            plan = controller.plan(PushRequest("R", "Bracket", "urn:x", "note"),
                                   [self.export("a.step", "x")], confirm=lambda q: True, ask_identity=None)
            controller.execute(plan, _UI())
        except (SettingsError, Exception):
            pass  # refused or failed: what matters is what was written
        handler.flush()
        written = {
            "log": open(log_path, encoding="utf-8", errors="replace").read(),
            "settings": open(settings, encoding="utf-8").read(),
            "git config": open(os.path.join(self.work, ".git", "config"), encoding="utf-8").read(),
        }
        for name, text in written.items():
            self.assertNotIn(TOKEN, text, name)
            self.assertNotIn(token_form, text, name)
            self.assertNotIn(base64.b64encode(TOKEN.encode()).decode(), text, name)


class NameTests(unittest.TestCase):
    def test_only_a_trailing_version_number_is_dropped_from_design_names(self):
        self.assertEqual(_safe_base("Bracket v2"), "Bracket")
        self.assertEqual(_safe_base("Flower vase"), "Flower vase")
        self.assertEqual(_safe_base("Water valve"), "Water valve")
        self.assertEqual(_safe_base("Arm v12"), "Arm")


class EditAddressTests(GitSandbox):
    def test_an_edited_address_must_look_like_a_repository_address(self):
        store = SettingsStore(os.path.join(self.base, "s.json"))
        store.load()
        store.add("R", {"path": self.work, "url": "https://github.com/acme/designs.git"})
        controller = PushController(store, MemoryCredentialStore())
        for bad in ("--upload-pack=evil", "not an address", "file:///etc"):
            with self.assertRaises(SettingsError, msg=bad):
                controller.edit_profile("R", url=bad)
        controller.edit_profile("R", url="https://github.com/acme/other.git")
        self.assertEqual(store.get("R")["url"], "https://github.com/acme/other.git")


if __name__ == "__main__":
    unittest.main()
