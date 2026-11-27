"""Settings persistence: migration, atomic saves, recovery and profile edits."""

import json
import os
import tempfile
import unittest
from unittest import mock

import _paths  # also puts src/ on sys.path
import settings_store as ss

V0 = {
    "Designs": {
        "url": "https://github.com/acme/designs.git",
        "path": "C:/Users/me/FusionGitRepos/Designs",
        "exportFormats": ["f3d", "step"],
        "skipPullDefault": True,
        "lastBranchPreview": "old-branch",
    },
    "__meta__": {"lastSelectedRepo": "Designs", "globalLogLevel": "INFO"},
}


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ftg_settings_")
        self.path = os.path.join(self.dir, ".fusion_git_repos.json")

    def tearDown(self):
        _paths.force_rmtree(self.dir)

    def write(self, content, raw=False, path=None):
        with open(path or self.path, "wb") as fh:
            fh.write(content if raw else json.dumps(content).encode("utf-8"))

    def files(self):
        return sorted(os.listdir(self.dir))

    def test_missing_file_starts_empty_and_creates_nothing(self):
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(store.profile_names(), [])
        self.assertEqual(report.messages, [])
        self.assertEqual(self.files(), [])

    def test_v0_is_migrated_and_backed_up_once_before_first_save(self):
        self.write(V0)
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(report.migrated_from, 0)
        self.assertEqual(store.profile_names(), ["Designs"])
        profile = store.get("Designs")
        self.assertNotIn("skipPullDefault", profile)  # obsolete force-push setting dropped
        self.assertNotIn("lastBranchPreview", profile)
        self.assertEqual(store.meta["lastSelectedRepo"], "Designs")
        # Loading alone never rewrites the file.
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), V0)
        store.save()
        with open(self.path + ".v0-backup", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), V0)
        with open(self.path, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["schemaVersion"], ss.SCHEMA_VERSION)
        self.assertIn("Designs", saved["repositories"])
        store.save()  # a second save doesn't create another backup
        self.assertEqual([f for f in self.files() if "v0" in f], [".fusion_git_repos.json.v0-backup"])

    def test_byte_order_mark_is_accepted(self):
        self.write(b"\xef\xbb\xbf" + json.dumps(V0).encode("utf-8"), raw=True)
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(store.profile_names(), ["Designs"])
        self.assertIsNone(report.backup_path)

    def test_corrupt_file_is_preserved_and_reported(self):
        self.write(b'{"Designs": {"path": "C:/x"', raw=True)
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(store.profile_names(), [])
        self.assertIsNotNone(report.backup_path)
        with open(report.backup_path, "rb") as fh:
            self.assertEqual(fh.read(), b'{"Designs": {"path": "C:/x"')
        self.assertTrue(any("couldn't be read" in m for m in report.messages))
        self.assertFalse(report.read_only)
        # Opening again with the same damaged file reuses the copy.
        again = ss.SettingsStore(self.path).load()
        self.assertEqual(again.backup_path, report.backup_path)
        self.assertEqual(len([f for f in self.files() if ".corrupt-" in f]), 1)

    def test_corrupt_file_without_backup_is_never_overwritten(self):
        self.write(b"not json", raw=True)
        store = ss.SettingsStore(self.path)
        with mock.patch.object(ss, "_write_private", side_effect=OSError("disk full")):
            report = store.load()
        self.assertTrue(report.read_only)
        with self.assertRaises(ss.SettingsError):
            store.save()
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), b"not json")

    def test_interrupted_save_with_complete_temp_file_is_finished(self):
        self.write(V0)
        newer = ss.migrate(V0)
        newer["meta"]["lastCommitMessage"] = "newer"
        self.write(newer, path=self.path + ".tmp")
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertTrue(report.recovered_from_temp)
        self.assertEqual(store.meta["lastCommitMessage"], "newer")
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_interrupted_save_with_partial_temp_file_keeps_the_original(self):
        self.write(V0)
        self.write(b'{"schemaVersion": 1, "repos', raw=True, path=self.path + ".tmp")
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertFalse(report.recovered_from_temp)
        self.assertEqual(store.profile_names(), ["Designs"])
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        self.assertTrue(any("incomplete" in f for f in self.files()), self.files())

    def test_save_is_atomic_when_the_write_fails(self):
        self.write(ss.migrate(V0))
        store = ss.SettingsStore(self.path)
        store.load()
        store.update("Designs", {"defaultMessage": "changed"})
        with mock.patch.object(ss.os, "replace", side_effect=OSError("crash during rename")):
            with self.assertRaises(OSError):
                store.save()
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), ss.migrate(V0))  # the original is intact
        # ...and the completed temp file is picked up on the next load.
        recovered = ss.SettingsStore(self.path)
        self.assertTrue(recovered.load().recovered_from_temp)
        self.assertEqual(recovered.get("Designs")["defaultMessage"], "changed")

    def test_newer_schema_is_read_only(self):
        future = {"schemaVersion": ss.SCHEMA_VERSION + 1, "repositories": {"X": {"path": "C:/x"}}, "meta": {}}
        self.write(future)
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertTrue(report.read_only)
        self.assertEqual(store.profile_names(), ["X"])
        with self.assertRaises(ss.SettingsError):
            store.save()
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), future)

    def test_invalid_profiles_are_hidden_but_kept(self):
        data = ss.migrate(V0)
        data["repositories"]["Broken"] = {"path": 42, "exportFormats": "f3d"}
        self.write(data)
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(store.profile_names(), ["Designs"])
        self.assertIn("Broken", report.invalid_profiles)
        store.save()
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["repositories"]["Broken"], {"path": 42, "exportFormats": "f3d"})

    def test_add_edit_rename_remove(self):
        store = ss.SettingsStore(self.path)
        store.load()
        store.add("Parts", {"path": "C:/parts", "url": "https://github.com/a/parts.git"})
        store.meta["lastSelectedRepo"] = "Parts"
        with self.assertRaises(ss.SettingsError):
            store.add("Parts", {"path": "C:/other"})
        with self.assertRaises(ss.SettingsError):
            store.add("__meta__", {"path": "C:/x"})
        with self.assertRaises(ss.SettingsError):
            store.update("Parts", {"path": ""})  # edits are validated
        self.assertEqual(store.get("Parts")["path"], "C:/parts")
        store.update("Parts", {"url": "https://github.com/a/parts2.git"})
        self.assertEqual(store.rename("Parts", "Parts 2026"), "Parts 2026")
        self.assertEqual(store.meta["lastSelectedRepo"], "Parts 2026")
        self.assertIsNone(store.get("Parts"))
        removed = store.remove("Parts 2026")
        self.assertEqual(removed["url"], "https://github.com/a/parts2.git")
        self.assertNotIn("lastSelectedRepo", store.meta)
        store.save()
        reloaded = ss.SettingsStore(self.path)
        reloaded.load()
        self.assertEqual(reloaded.profile_names(), [])

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_files_are_owner_only_on_posix(self):
        store = ss.SettingsStore(self.path)
        store.load()
        store.add("A", {"path": "/tmp/a"})
        store.save()
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_design_folders_are_stable_and_never_shared(self):
        profile = {"path": "C:/x"}
        self.assertEqual(ss.design_folder(profile, "id-1", "Bracket"), "Bracket")
        self.assertEqual(ss.design_folder(profile, "id-2", "Bracket"), "Bracket (2)")  # name collision
        self.assertEqual(ss.design_folder(profile, "id-1", "Bracket v2 renamed"), "Bracket")  # rename keeps it
        self.assertEqual(ss.design_folder(profile, "id-3", 'Bad:Name/"x"'), "Bad_Name_x_")
        self.assertEqual(ss.design_folder(profile, "id-4", "CON"), "CON_")
        self.assertEqual(profile["designs"]["id-1"]["name"], "Bracket v2 renamed")


class ReviewFixSettingsTests(unittest.TestCase):
    """Regressions for the S3 independent review findings."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ftg_settings_")
        self.path = os.path.join(self.dir, ".fusion_git_repos.json")

    def tearDown(self):
        _paths.force_rmtree(self.dir)

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_wrong_shapes_with_the_right_version_never_crash(self):
        for bad in ({"schemaVersion": 1, "repositories": [], "meta": None},
                    {"schemaVersion": 1, "repositories": {"A": "not an object"}}):
            with self.subTest(bad=bad):
                self.write(bad)
                store = ss.SettingsStore(self.path)
                store.load()
                self.assertEqual(store.profile_names(), [])
                self.assertIsInstance(store.meta, dict)

    def test_profile_with_a_token_in_its_address_is_hidden(self):
        self.write({"schemaVersion": 1, "meta": {}, "repositories": {
            "Leaky": {"path": "C:/x", "url": "https://u:ghp_" + "k" * 36 + "@github.com/a/b.git"}}})
        store = ss.SettingsStore(self.path)
        report = store.load()
        self.assertEqual(store.profile_names(), [])
        self.assertIn("Leaky", report.invalid_profiles)

    def test_adding_the_name_of_a_hidden_profile_explains_why(self):
        self.write({"schemaVersion": 1, "meta": {}, "repositories": {"Broken": {"path": 1}}})
        store = ss.SettingsStore(self.path)
        store.load()
        with self.assertRaises(ss.SettingsError) as ctx:
            store.add("Broken", {"path": "C:/y"})
        self.assertIn("hidden", str(ctx.exception))

    def test_unsaved_design_keeps_its_folder_once_saved_to_the_cloud(self):
        profile = {"path": "x"}
        self.assertEqual(ss.design_folder(profile, "name:Bracket", "Bracket"), "Bracket")
        self.assertEqual(ss.design_folder(profile, "urn:adsk.wipprod:dm.lineage:abc", "Bracket"), "Bracket")
        self.assertNotIn("name:Bracket", profile["designs"])
        # A different, unrelated design with that name still gets its own folder.
        self.assertEqual(ss.design_folder(profile, "urn:other", "Bracket"), "Bracket (2)")

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_backup_copies_are_owner_only(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        report = ss.SettingsStore(self.path).load()
        self.assertEqual(os.stat(report.backup_path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
