"""Portable names, export file checks and synced-folder detection (no Fusion)."""

import os
import struct
import tempfile
import unittest
import zipfile
from unittest import mock

import _paths

import dialog_helpers as dh
import export_checks as ec
import portable_names as pn


class PortableNameTests(unittest.TestCase):
    def test_names(self):
        cases = {
            "Bracket": "Bracket",
            'Bad:Name/"x"': "Bad_Name_x_",
            "..\\..\\escape": "_.._escape",
            "  trailing dots... ": "trailing dots",
            "CON": "CON_",
            "con.step": "con_.step",
            "LPT9 assembly": "LPT9 assembly",
            "nul": "nul_",
            "tab\tand\nnewline": "tab and newline",
            "": "Design",
            "...": "Design",
            "Halterung für Motor": "Halterung für Motor",
        }
        for raw, expected in cases.items():
            self.assertEqual(pn.portable_name(raw), expected, repr(raw))

    def test_unicode_is_normalised_so_macos_and_windows_agree(self):
        decomposed = "Kaffé"  # e + combining acute (as macOS may give it)
        self.assertEqual(pn.portable_name(decomposed), "Kaffé")

    def test_length_is_capped_without_trailing_dots(self):
        name = pn.portable_name("a" * 99 + ". extra", max_length=100)
        self.assertLessEqual(len(name), 100)
        self.assertFalse(name.endswith((".", " ")))

    def test_deterministic(self):
        self.assertEqual(pn.portable_name("Arm <v2>"), pn.portable_name("Arm <v2>"))

    def test_unique_names_ignore_case(self):
        self.assertEqual(pn.unique_names(["Part.stl", "part.stl", "PART.stl", "Other.stl"]),
                         ["Part.stl", "part (2).stl", "PART (3).stl", "Other.stl"])
        self.assertEqual(pn.case_collisions(["A.stl", "a.STL", "b.stl"]), [["A.stl", "a.STL"]])


class ExportCheckTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ftg_checks_")
        self.addCleanup(_paths.force_rmtree, self.dir)

    def file(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def f3d(self, name="Part.f3d"):
        path = os.path.join(self.dir, name)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Manifest.dat", "x")
        return path

    def stl_binary(self, name="Part.stl", triangles=2, truncate=0):
        data = b"\0" * 80 + struct.pack("<I", triangles) + b"\0" * (50 * triangles - truncate)
        return self.file(name, data)

    def test_valid_files_pass(self):
        files = {
            "f3d": [self.f3d()],
            "step": [self.file("Part.step", b"ISO-10303-21;\nHEADER;")],
            "stl": [self.stl_binary(), self.file("Ascii.stl", b"solid x\n facet normal 0 0 1\nendsolid")],
            "iges": [self.file("Part.igs", b" " * 72 + b"S      1\n")],
            "sat": [self.file("Part.sat", b"700 0 1 0\n")],
        }
        self.assertEqual(ec.check_exports(files, ["f3d", "step", "stl", "iges", "sat"]), [])

    def test_failures_are_reported(self):
        problems = ec.check_exports({
            "f3d": [self.file("Bad.f3d", b"not a zip")],
            "step": [self.file("Empty.step", b"")],
            "stl": [self.stl_binary("Cut.stl", truncate=10)],
        }, ["f3d", "step", "stl", "iges"])
        text = "\n".join(problems)
        self.assertIn("Bad.f3d is not a Fusion archive", text)
        self.assertIn("Empty.step is empty", text)
        self.assertIn("Cut.stl is not a complete STL file", text)
        self.assertIn("The IGES export produced no file", text)

    def test_missing_wrong_extension_too_large_and_colliding(self):
        self.assertIn("was not created", ec.check_export(os.path.join(self.dir, "nope.step"), "step"))
        self.assertIn("doesn't have a STEP file extension", ec.check_export(self.file("x.txt", b"ISO-10303-21"), "step"))
        big = self.file("Big.step", b"ISO-10303-21")
        with mock.patch.object(ec.os.path, "getsize", return_value=ec.SIZE_LIMIT_BYTES):
            self.assertIn("100 MB", ec.check_export(big, "step"))
        problems = ec.check_exports({"stl": [self.stl_binary("Arm.stl"), self.stl_binary("ARM2.stl")],
                                     "step": [self.file("arm.STL.step", b"ISO-10303-21")]}, ["stl"])
        self.assertEqual(problems, [])
        clash = ec.check_exports({"stl": [self.stl_binary("Arm.stl")], "f3d": [self.f3d("ARM.stl")]}, ["stl"])
        self.assertTrue(any("overwrite each other" in p for p in clash), clash)


class SyncedFolderTests(unittest.TestCase):
    def test_detects_common_sync_services(self):
        cases = {
            os.path.join("C:", os.sep, "Users", "me", "OneDrive", "Designs"): "OneDrive",
            os.path.join("C:", os.sep, "Users", "me", "OneDrive - Acme", "CAD"): "OneDrive",
            os.path.join("C:", os.sep, "Users", "me", "Dropbox", "CAD"): "Dropbox",
            "/Users/me/Library/Mobile Documents/com~apple~CloudDocs/CAD": "iCloud Drive",
            os.path.join("G:", os.sep, "My Drive", "CAD"): "Google Drive",
            os.path.join("C:", os.sep, "Users", "me", "FusionGitRepos", "Designs"): None,
        }
        with mock.patch.dict(os.environ, {"OneDrive": "", "OneDriveConsumer": "", "OneDriveCommercial": ""}):
            for path, expected in cases.items():
                self.assertEqual(dh.synced_folder_service(path), expected, path)

    def test_onedrive_env_folder_is_detected_whatever_its_name(self):
        root = os.path.join("D:", os.sep, "Sync", "CompanyCloud")
        with mock.patch.dict(os.environ, {"OneDriveCommercial": root}):
            self.assertEqual(dh.synced_folder_service(os.path.join(root, "CAD")), "OneDrive")

    def test_validation_warns_but_does_not_block(self):
        base = tempfile.mkdtemp(prefix="ftg_sync_")
        self.addCleanup(_paths.force_rmtree, base)
        folder = os.path.join(base, "Dropbox", "Designs")
        os.makedirs(os.path.join(folder, ".git"))
        result = dh.validate_repo_inputs("Saved", folder, "", "__new__")
        self.assertTrue(result["ok"])
        self.assertIn("Dropbox", result["messages"]["path"][0])


if __name__ == "__main__":
    unittest.main()
