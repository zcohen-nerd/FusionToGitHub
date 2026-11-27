"""Push workflow and profile management (push_controller), end to end with real git."""

import os
import unittest
from unittest import mock

import _paths  # noqa: F401
from test_core_identity_history import GitSandbox, _UI

import fusion_git_core as core
from credentials import CredentialError, MemoryCredentialStore
from push_controller import (
    PushCancelled,
    PushController,
    PushRefused,
    PushRequest,
    design_destination,
    server_of,
)
from settings_store import SettingsError, SettingsStore


class ControllerTestCase(GitSandbox):
    def setUp(self):
        super().setUp()
        self.settings_path = os.path.join(self.base, "settings.json")
        self.store = SettingsStore(self.settings_path)
        self.store.load()
        self.store.add("Designs", {
            "path": self.work,
            "url": "https://github.com/acme/designs.git",
            "exportFormats": ["step"],
            "historyMode": core.MODE_SINGLE,
        })
        self.creds = MemoryCredentialStore()
        self.controller = PushController(self.store, self.creds)
        self.questions = []

    def confirm_yes(self, question):
        self.questions.append(question)
        return True

    def ask_identity(self, name="Ada Lovelace", email="ada@example.invalid", everywhere=False):
        calls = []

        def ask():
            calls.append(1)
            return (name, email, everywhere)

        ask.calls = calls
        return ask

    def request(self, **kw):
        defaults = dict(profile_name="Designs", design_name="Bracket", design_id="urn:id:1", commit_message="holes 5mm")
        defaults.update(kw)
        return PushRequest(**defaults)


class PlanTests(ControllerTestCase):
    def test_declining_the_publication_notice_cancels_and_is_asked_again(self):
        with self.assertRaises(PushCancelled):
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=lambda q: False)
        self.assertFalse(self.store.get("Designs").get("publicationNoticeAccepted"))

    def test_notice_is_shown_once_and_names_the_destination(self):
        ask = self.ask_identity()
        self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes, ask_identity=ask)
        self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes, ask_identity=ask)
        self.assertEqual(len(self.questions), 1)
        self.assertIn("github.com/acme/designs", self.questions[0])

    def test_identity_is_saved_in_the_profile_not_in_git_config(self):
        repo_config = os.path.join(self.work, ".git", "config")
        before = (self.digest(repo_config), self.digest(self.global_config))
        ask = self.ask_identity()
        plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes, ask_identity=ask)
        self.assertEqual(plan.identity, {"name": "Ada Lovelace", "email": "ada@example.invalid"})
        self.assertEqual(self.store.get("Designs")["gitIdentity"]["email"], "ada@example.invalid")
        self.assertEqual((self.digest(repo_config), self.digest(self.global_config)), before)
        # Saved: not asked again.
        self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes, ask_identity=ask)
        self.assertEqual(len(ask.calls), 1)
        # And it survived a save/reload.
        reloaded = SettingsStore(self.settings_path)
        reloaded.load()
        self.assertEqual(reloaded.get("Designs")["gitIdentity"]["name"], "Ada Lovelace")

    def test_global_identity_only_with_explicit_opt_in(self):
        plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes,
                                    ask_identity=self.ask_identity(everywhere=True))
        self.assertIsNotNone(plan.identity)
        with open(self.global_config, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("ada@example.invalid", text)

    def test_existing_git_identity_is_used_without_asking(self):
        core.git_run(self.work, "config", "--global", "user.name", "Configured")
        core.git_run(self.work, "config", "--global", "user.email", "configured@example.invalid")
        ask = self.ask_identity()
        plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes, ask_identity=ask)
        self.assertIsNone(plan.identity)
        self.assertEqual(ask.calls, [])

    def test_bad_identity_answers_are_refused(self):
        for answer in [None, ("", "a@b.invalid", False), ("Ada", "not-an-email", False)]:
            with self.subTest(answer=answer), self.assertRaises((PushCancelled, PushRefused)):
                self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes,
                                     ask_identity=lambda a=answer: a)

    def test_stored_token_required_when_enabled(self):
        # The saved GitHub address is the folder's own address (as after setup).
        core.git_run(self.work, "remote", "set-url", "origin", self.store.get("Designs")["url"])
        self.store.update("Designs", {"useStoredPat": True, "gitIdentity": {"name": "A", "email": "a@b.invalid"}})
        with self.assertRaises(PushRefused):
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.creds.set("Designs", "", "ghp_" + "z" * 36)
        plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertEqual(plan.pat_credentials["token"], "ghp_" + "z" * 36)
        self.assertNotIn("ghp_", repr(plan))

    def test_refuses_missing_folder_and_empty_exports(self):
        with self.assertRaises(PushRefused):
            self.controller.plan(self.request(), [], confirm=self.confirm_yes)
        self.store.update("Designs", {"path": os.path.join(self.base, "nowhere")})
        with self.assertRaises(PushRefused):
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)

    def test_design_destination(self):
        profile = {"path": "x"}
        self.assertEqual(design_destination(profile, "id1", "Bracket"), ("Bracket", "Bracket/HISTORY.md"))
        self.assertEqual(design_destination(profile, "id2", "Bracket")[0], "Bracket (2)")
        profile2 = {"path": "x", "exportSubfolder": "cad/exports"}
        self.assertEqual(design_destination(profile2, "id1", "Arm")[0], "cad/exports/Arm")
        profile3 = {"path": "x", "exportSubfolder": "parts/{filename}/step"}
        self.assertEqual(design_destination(profile3, "id1", "Arm"), ("parts/Arm/step", "parts/Arm/step/HISTORY.md"))


class ExecuteTests(ControllerTestCase):
    def test_full_push_lays_out_per_design_folders_and_history(self):
        ask = self.ask_identity()
        for design_id, name, content in [("urn:1", "Bracket", "v1"), ("urn:2", "Bracket", "other"), ("urn:1", "Bracket", "v2")]:
            plan = self.controller.plan(self.request(design_id=design_id, design_name=name),
                                        [self.export("Bracket.step", content)], confirm=self.confirm_yes, ask_identity=ask)
            ui = _UI()
            self.assertTrue(self.controller.execute(plan, ui), ui.errors)
        files = sorted(core.git_run(self.origin, "ls-tree", "-r", "--name-only", "main").stdout.splitlines())
        self.assertEqual(files, [".gitattributes", "Bracket (2)/Bracket.step", "Bracket (2)/HISTORY.md",
                                 "Bracket/Bracket.step", "Bracket/HISTORY.md"])
        self.assertEqual(self.show("main:Bracket/Bracket.step"), "v2")
        self.assertEqual(self.show("main:Bracket/HISTORY.md").count("## "), 2)
        author = core.git_run(self.origin, "log", "-1", "--format=%ae", "main").stdout.strip()
        self.assertEqual(author, "ada@example.invalid")


class ProfileTests(ControllerTestCase):
    def test_remove_keeps_folder_history_and_token_unless_asked(self):
        self.creds.set("Designs", "", "ghp_" + "t" * 36)
        head_before = core.git_run(self.work, "rev-parse", "--git-dir").stdout
        self.controller.remove_profile("Designs")
        self.assertIsNone(self.store.get("Designs"))
        self.assertTrue(os.path.isdir(os.path.join(self.work, ".git")))
        self.assertEqual(core.git_run(self.work, "rev-parse", "--git-dir").stdout, head_before)
        self.assertIsNotNone(self.creds.get("Designs"))  # token kept
        self.store.add("Designs", {"path": self.work})
        self.controller.remove_profile("Designs", delete_token=True)
        self.assertIsNone(self.creds.get("Designs"))

    def test_rename_moves_the_token(self):
        self.creds.set("Designs", "u", "ghp_" + "r" * 36)
        final, notes = self.controller.edit_profile("Designs", new_name="Parts")
        self.assertEqual(final, "Parts")
        self.assertIsNone(self.creds.get("Designs"))
        self.assertEqual(self.creds.get("Parts")["token"], "ghp_" + "r" * 36)

    def test_address_change_to_another_host_disables_the_token_and_reasks_notice(self):
        self.store.update("Designs", {"useStoredPat": True, "publicationNoticeAccepted": True})
        origin_before = core.git_run(self.work, "remote", "get-url", "origin").stdout
        final, notes = self.controller.edit_profile(
            "Designs", url="https://gitlab.example.invalid/acme/designs.git", update_origin=lambda *a: False
        )
        profile = self.store.get("Designs")
        self.assertFalse(profile["useStoredPat"])
        self.assertFalse(profile["publicationNoticeAccepted"])
        self.assertEqual(core.git_run(self.work, "remote", "get-url", "origin").stdout, origin_before)
        self.assertTrue(any("Use Stored Token" in n for n in notes))

    def test_address_change_updates_origin_only_when_confirmed(self):
        self.controller.edit_profile("Designs", url="https://github.com/acme/renamed.git", update_origin=lambda *a: True)
        self.assertEqual(core.git_run(self.work, "remote", "get-url", "origin").stdout.strip(),
                         "https://github.com/acme/renamed.git")
        self.assertTrue(self.store.get("Designs").get("useStoredPat") is not True)

    def test_edits_are_validated(self):
        with self.assertRaises(SettingsError):
            self.controller.edit_profile("Designs", url="https://u:ghp_" + "s" * 36 + "@github.com/a/b.git")
        with self.assertRaises(SettingsError):
            self.controller.edit_profile("Designs", path=os.path.join(self.base, "not-a-repo"))
        self.store.add("Other", {"path": self.work})
        with self.assertRaises(SettingsError):
            self.controller.edit_profile("Designs", new_name="Other")


class ReviewFixTests(ControllerTestCase):
    """Regressions for the S3 independent review findings."""

    TOKEN = "ghp_" + "h" * 36

    def use_https_origin(self, url="https://github.com/acme/designs.git"):
        # The folder's own address (fetch and push); nothing here contacts a
        # server. Only a push *URL* would be a redirect, which token pushes
        # refuse (R-21).
        core.git_run(self.work, "remote", "set-url", "origin", url)

    def ready_profile(self, **changes):
        changes.setdefault("gitIdentity", {"name": "A", "email": "a@b.invalid"})
        changes.setdefault("publicationNoticeAccepted", True)
        self.store.update("Designs", changes)

    def test_token_is_bound_to_its_server_and_refused_elsewhere(self):
        self.use_https_origin()
        self.ready_profile(useStoredPat=True)
        self.assertEqual(self.controller.store_token("Designs", "", self.TOKEN), "github.com")
        self.assertEqual(self.creds.get("Designs")["host"], "github.com")
        plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertEqual(plan.pat_credentials["token"], self.TOKEN)
        # The same profile pointed at a clone on another server: refused.
        self.use_https_origin("https://git.evil.example.invalid/acme/designs.git")
        with self.assertRaises(PushRefused) as ctx:
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertIn("saved for github.com", str(ctx.exception))
        self.assertNotIn(self.TOKEN, str(ctx.exception))

    def test_kept_token_is_not_inherited_by_a_new_profile_on_another_server(self):
        self.use_https_origin()
        self.ready_profile(useStoredPat=True)
        self.controller.store_token("Designs", "", self.TOKEN)
        self.controller.remove_profile("Designs", delete_token=False)
        self.store.add("Designs", {"path": self.work, "url": "https://git.evil.example.invalid/x.git",
                                   "useStoredPat": True, "publicationNoticeAccepted": True,
                                   "gitIdentity": {"name": "A", "email": "a@b.invalid"}})
        self.use_https_origin("https://git.evil.example.invalid/x.git")
        with self.assertRaises(PushRefused):
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)

    def test_token_saved_before_0_5_is_bound_on_first_use(self):
        self.use_https_origin()
        self.ready_profile(useStoredPat=True)
        self.creds.set("Designs", "", self.TOKEN)  # no host, as 0.4.0 stored it
        self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertEqual(self.creds.get("Designs")["host"], "github.com")

    def test_a_token_push_to_another_repository_is_refused_in_the_dialog(self):
        # R-21 follow-up (E3): a push URL to another repository on the same
        # server would have received the token; refused before the push.
        self.use_https_origin()
        self.ready_profile(useStoredPat=True)
        self.controller.store_token("Designs", "", self.TOKEN)
        core.git_run(self.work, "remote", "set-url", "--push", "origin", "https://github.com/attacker/loot.git")
        with self.assertRaises(PushRefused) as ctx:
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertIn("attacker/loot", str(ctx.exception))
        self.assertNotIn(self.TOKEN, str(ctx.exception))
        # And a folder whose address differs from the one saved for it.
        core.git_run(self.work, "remote", "set-url", "--delete", "--push", "origin", "https://github.com/attacker/loot.git")
        core.git_run(self.work, "remote", "set-url", "origin", "https://github.com/acme/other.git")
        with self.assertRaises(PushRefused) as ctx:
            self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes)
        self.assertIn("acme/designs", str(ctx.exception))

    def test_failed_edit_changes_nothing(self):
        self.store.add("Other", {"path": self.work})
        self.store.save()
        origin_before = core.git_run(self.work, "remote", "get-url", "origin").stdout
        profile_before = dict(self.store.get("Designs"))
        asked = []
        with self.assertRaises(SettingsError):
            self.controller.edit_profile("Designs", new_name="Other", url="https://github.com/acme/new.git",
                                         update_origin=lambda *a: asked.append(1) or True)
        self.assertEqual(asked, [])  # refused before asking anything
        self.assertEqual(self.store.get("Designs"), profile_before)
        self.assertEqual(core.git_run(self.work, "remote", "get-url", "origin").stdout, origin_before)
        reloaded = SettingsStore(self.settings_path)
        reloaded.load()
        self.assertEqual(reloaded.get("Designs")["url"], profile_before["url"])

    def test_edit_rolls_back_when_the_save_fails(self):
        before = dict(self.store.get("Designs"))
        with mock.patch.object(self.store, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.controller.edit_profile("Designs", new_name="Renamed", url="https://github.com/acme/x.git",
                                             update_origin=lambda *a: True)
        self.assertEqual(self.store.get("Designs"), before)
        self.assertIsNone(self.store.get("Renamed"))
        self.assertNotIn("x.git", core.git_run(self.work, "remote", "get-url", "origin").stdout)

    def test_folder_change_turns_off_the_stored_token(self):
        other = os.path.join(self.base, "other-clone")
        core.git_run(self.base, "clone", self.origin, other)
        self.store.update("Designs", {"useStoredPat": True})
        _, notes = self.controller.edit_profile("Designs", path=other)
        self.assertFalse(self.store.get("Designs")["useStoredPat"])
        self.assertTrue(any("different folder" in n for n in notes))

    def test_remove_deletes_the_token_only_after_settings_are_saved(self):
        self.creds.set("Designs", "", self.TOKEN)
        self.store.report.read_only = True
        with self.assertRaises(SettingsError):
            self.controller.remove_profile("Designs", delete_token=True)
        self.assertIsNotNone(self.creds.get("Designs"))  # token untouched
        self.assertIsNotNone(self.store.get("Designs"))  # entry untouched
        self.store.report.read_only = False
        with mock.patch.object(self.creds, "delete", side_effect=CredentialError("vault locked")):
            removed, notes = self.controller.remove_profile("Designs", delete_token=True)
        self.assertIsNone(self.store.get("Designs"))
        self.assertTrue(any("vault locked" in n for n in notes))

    def test_global_identity_failure_still_saves_it_for_the_repository(self):
        broken_global = os.path.join(self.base, "not-a-file")
        os.makedirs(broken_global)  # git can't write a directory
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": broken_global}):
            plan = self.controller.plan(self.request(), [self.export("a.step", "A")], confirm=self.confirm_yes,
                                        ask_identity=self.ask_identity(everywhere=True))
        self.assertEqual(plan.identity["email"], "ada@example.invalid")
        self.assertEqual(self.store.get("Designs")["gitIdentity"]["email"], "ada@example.invalid")
        self.assertTrue(any("all repositories" in n for n in plan.notes))

    def test_server_of(self):
        cases = {
            "https://github.com/a/b.git": "github.com",
            "https://GitHub.com:8443/a/b.git": "github.com:8443",
            "git@github.com:a/b.git": "github.com",
            "ssh://git@github.com/a/b.git": "github.com",
            "C:/local/repo": "",
            "": "",
        }
        for url, expected in cases.items():
            self.assertEqual(server_of(url), expected, url)

    def test_timestamp_subfolder_keeps_one_history_per_design(self):
        profile = {"path": "x", "exportSubfolder": "exports/{timestamp}"}
        folder, history = design_destination(profile, "id1", "Arm")
        self.assertTrue(folder.startswith("exports/") and folder.endswith("/Arm") and folder != "exports/Arm")
        self.assertEqual(history, "exports/Arm/HISTORY.md")
        profile2 = {"path": "x", "exportSubfolder": "{filename}/v{timestamp}"}
        folder2, history2 = design_destination(profile2, "id1", "Arm")
        self.assertTrue(folder2.startswith("Arm/v"))
        self.assertEqual(history2, "Arm/HISTORY.md")


if __name__ == "__main__":
    unittest.main()
