"""Push workflow and profile management (push_controller), end to end with real git."""

import os
import unittest

import _paths  # noqa: F401
from test_core_identity_history import GitSandbox, _UI

import fusion_git_core as core
from credentials import MemoryCredentialStore
from push_controller import PushCancelled, PushController, PushRefused, PushRequest, design_destination
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


if __name__ == "__main__":
    unittest.main()
