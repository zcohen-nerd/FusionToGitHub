"""Credential store behaviour.

The Windows Credential Manager test only runs when FTG_REAL_VAULT_TESTS=1
(set by the Windows CI jobs), so it never writes to a developer's own vault
by accident.
"""

import os
import unittest
import uuid

import _paths  # noqa: F401
import credentials as cr


class CredentialStoreContract:
    """Behaviour every available store must have."""

    def make(self):
        raise NotImplementedError

    def test_set_get_rename_delete(self):
        store = self.make()
        name = f"ftg-test-{uuid.uuid4().hex[:8]}"
        renamed = name + "-renamed"
        try:
            self.assertIsNone(store.get(name))
            store.set(name, "octocat", "ghp_" + "x" * 36)  # as before 0.5.0: no server
            self.assertEqual(store.get(name), {"username": "octocat", "token": "ghp_" + "x" * 36, "host": ""})
            store.set(name, "", "ghp_" + "y" * 36, "github.com")  # replacing, bound to a server
            self.assertEqual(store.get(name)["token"], "ghp_" + "y" * 36)
            self.assertEqual(store.get(name)["host"], "github.com")
            store.rename(name, renamed)
            self.assertIsNone(store.get(name))
            self.assertEqual(store.get(renamed)["token"], "ghp_" + "y" * 36)
            self.assertEqual(store.get(renamed)["host"], "github.com")  # the binding moves too
            store.delete(renamed)
            store.delete(renamed)  # deleting twice is fine
            self.assertIsNone(store.get(renamed))
            with self.assertRaises(cr.CredentialError):
                store.set(name, "", "")
        finally:
            store.delete(name)
            store.delete(renamed)


class MemoryStoreTests(CredentialStoreContract, unittest.TestCase):
    def make(self):
        return cr.MemoryCredentialStore()

    def test_target_names_are_unchanged_from_earlier_versions(self):
        self.assertEqual(cr.target_name("My Repo"), "FusionToGitHub::My Repo")


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("FTG_REAL_VAULT_TESTS") == "1",
    "real Windows Credential Manager: only with FTG_REAL_VAULT_TESTS=1 (CI)",
)
class WindowsStoreTests(CredentialStoreContract, unittest.TestCase):
    def make(self):
        return cr.default_store()


class UnavailableStoreTests(unittest.TestCase):
    def test_reports_unavailable_and_refuses_to_store(self):
        store = cr.UnavailableCredentialStore()
        self.assertFalse(store.available)
        self.assertIsNone(store.get("x"))
        with self.assertRaises(cr.CredentialError):
            store.set("x", "", "token")
        store.delete("x")
        store.rename("x", "y")


if __name__ == "__main__":
    unittest.main()
