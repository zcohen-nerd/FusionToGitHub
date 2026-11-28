"""Design folders checked against GitHub (risk R-24), with real Git and a local "GitHub"."""

import unittest

import _paths  # noqa: F401
from test_core_identity_history import GitSandbox

import fusion_git_core as core
from push_controller import destination_for


class RecordingUI:
    def __init__(self):
        self.errors = []

    def info(self, message):
        pass

    def warn(self, message):
        pass

    def error(self, message):
        self.errors.append(message)

    def confirm(self, message):
        return True


class DesignFolderTests(GitSandbox):
    def push(self, design_id, folder, content="x", template="designs"):
        source = self.export("Bracket.step", content)
        ui = RecordingUI()

        def relocate(name):
            export_folder, history = destination_for(template, name)
            return [(source, f"{export_folder}/Bracket.step")], history

        exports, history = relocate(folder)
        result = core.push_export(
            self.work, exports, "{filename}: test", "Bracket", ui,
            mode=core.MODE_SINGLE, history_file=history, history_title="History: Bracket",
            identity=self.identity, design_id=design_id, design_folder=folder, relocate=relocate,
        )
        self.assertIsNotNone(result, ui.errors)
        return result

    def files(self):
        return core.git_run(self.origin, "ls-tree", "-r", "--name-only", "main").stdout.split("\n")

    def owner(self, folder):
        data = core.git_run(self.origin, "show", f"main:designs/{folder}/HISTORY.md").stdout.encode("utf-8")
        return core.history_owner(data)

    def test_folders_follow_the_markers_on_github(self):
        first = self.push("urn:one", "Bracket")
        self.assertEqual(first["design_folder"], "Bracket")
        self.assertEqual(self.owner("Bracket"), core.design_key("urn:one"))
        # Another computer gives a different design the same folder name.
        second = self.push("urn:two", "Bracket")
        self.assertEqual(second["design_folder"], "Bracket (2)")
        self.assertEqual(self.owner("Bracket (2)"), core.design_key("urn:two"))
        # A third computer that thinks design two belongs in "Bracket (3)"
        # finds its existing folder instead.
        again = self.push("urn:two", "Bracket (3)")
        self.assertEqual(again["design_folder"], "Bracket (2)")
        self.assertNotIn("designs/Bracket (3)/Bracket.step", self.files())
        # A taken name with a number moves to the next free one.
        third = self.push("urn:three", "Bracket (2)")
        self.assertEqual(third["design_folder"], "Bracket (3)")

    def test_a_history_without_a_marker_is_kept_and_marked(self):
        # Written before 0.7.0: nobody can tell whose it is, so it is kept.
        source = self.export("old.step", "old")
        core.push_export(self.work, [(source, "designs/Bracket/old.step")], "old", "Bracket", RecordingUI(),
                         mode=core.MODE_SINGLE, history_file="designs/Bracket/HISTORY.md",
                         history_title="History: Bracket", identity=self.identity)
        self.assertIsNone(self.owner("Bracket"))
        result = self.push("urn:one", "Bracket")
        self.assertEqual(result["design_folder"], "Bracket")
        self.assertEqual(self.owner("Bracket"), core.design_key("urn:one"))
        history = core.git_run(self.origin, "show", "main:designs/Bracket/HISTORY.md").stdout
        self.assertEqual(history.count("## "), 2)
        self.assertTrue(history.startswith("# History: Bracket\n<!-- fusion-to-github design: "))

    def test_a_folder_with_other_files_but_no_history_is_used(self):
        source = self.export("readme.txt", "notes")
        core.push_export(self.work, [(source, "designs/Bracket/readme.txt")], "notes", "Bracket", RecordingUI(),
                         mode=core.MODE_SINGLE, history_file=None, identity=self.identity)
        self.assertEqual(self.push("urn:one", "Bracket")["design_folder"], "Bracket")

    def test_markers(self):
        key = core.design_key("urn:adsk.wipprod:dm.lineage:abc")
        self.assertRegex(key, r"^[0-9a-f]{16}$")
        self.assertEqual(key, core.design_key("urn:adsk.wipprod:dm.lineage:abc"))
        marked = core._with_marker(b"# History: X\r\n\r\n## entry\r\n", key)
        self.assertEqual(marked.splitlines()[1], f"<!-- fusion-to-github design: {key} -->".encode())
        self.assertIn(b"\r\n", marked)
        self.assertEqual(core._with_marker(marked, key), marked)
        self.assertEqual(core.history_owner(marked), key)
        self.assertIsNone(core.history_owner(b"# History\n"))
        self.assertIsNone(core.history_owner(None))


if __name__ == "__main__":
    unittest.main()
