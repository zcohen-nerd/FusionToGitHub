"""Git core: commit identity without config changes (Q14), per-design history (Q11).

These run real git against local bare repositories, with the system and
global Git config replaced by empty files so the developer's own setup is
never read or changed.
"""

import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _paths  # noqa: F401
import fusion_git_core as core


class _UI:
    def __init__(self):
        self.errors, self.warnings = [], []

    def info(self, m):
        pass

    def warn(self, m):
        self.warnings.append(m)

    def error(self, m):
        self.errors.append(m)

    def confirm(self, m):
        return True


class GitSandbox(unittest.TestCase):
    """A bare origin and a clone, with an isolated (empty) Git configuration."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="ftg_core_")
        self.global_config = os.path.join(self.base, "global.gitconfig")
        open(self.global_config, "w").close()
        isolated = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": self.global_config,
            # No identity anywhere unless a test provides one.
            "GIT_AUTHOR_NAME": "",
            "GIT_AUTHOR_EMAIL": "",
            "GIT_COMMITTER_NAME": "",
            "GIT_COMMITTER_EMAIL": "",
        }
        patcher = mock.patch.dict(os.environ, isolated)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            os.environ.pop(key, None)
        self.origin = os.path.join(self.base, "origin.git")
        self.work = os.path.join(self.base, "work")
        core.git_run(self.base, "init", "--bare", "-b", "main", self.origin)
        core.git_run(self.base, "clone", self.origin, self.work)
        self.identity = {"name": "Ada Lovelace", "email": "ada@example.invalid"}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def export(self, name, content):
        folder = os.path.join(self.base, "exports")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def show(self, ref):
        return core.git_run(self.origin, "show", ref).stdout

    @staticmethod
    def digest(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()


class IdentityTests(GitSandbox):
    def test_identity_signs_the_commit_without_writing_any_config(self):
        repo_config = os.path.join(self.work, ".git", "config")
        before = (self.digest(repo_config), self.digest(self.global_config))
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "a.step")], "note", "Part", ui,
            mode=core.MODE_SINGLE, identity=self.identity,
        )
        self.assertTrue(result, ui.errors)
        author = core.git_run(self.origin, "log", "-1", "--format=%an <%ae> / %cn <%ce>", "main").stdout.strip()
        self.assertEqual(author, "Ada Lovelace <ada@example.invalid> / Ada Lovelace <ada@example.invalid>")
        # Both bootstrap and export commits were signed; no config changed.
        self.assertEqual(core.git_run(self.origin, "log", "--format=%an", "main").stdout.split("\n")[:2],
                         ["Ada Lovelace", "Ada Lovelace"])
        self.assertEqual((self.digest(repo_config), self.digest(self.global_config)), before)

    def test_without_identity_the_failure_is_explained(self):
        ui = _UI()
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": self.global_config}):
            core.git_run(self.work, "config", "user.useConfigOnly", "true")
            result = core.push_export(self.work, [(self.export("a.step", "A"), "a.step")], "n", "Part", ui)
        self.assertIsNone(result)
        self.assertTrue(any("name and email" in e for e in ui.errors), ui.errors)


class HistoryTests(GitSandbox):
    def push(self, rel_history, legacy=None, title=None, content="v"):
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("Bracket.step", content), "designs/Bracket/Bracket.step")],
            "note {filename}", "Bracket", ui, mode=core.MODE_SINGLE, identity=self.identity,
            history_file=rel_history, history_title=title, legacy_history_file=legacy,
        )
        self.assertTrue(result, ui.errors)
        return result

    def test_per_design_history_accumulates_under_its_title(self):
        self.push("designs/Bracket/HISTORY.md", title="History: Bracket", content="v1")
        self.push("designs/Bracket/HISTORY.md", title="History: Bracket", content="v2")
        text = self.show("main:designs/Bracket/HISTORY.md")
        self.assertTrue(text.startswith("# History: Bracket\n\n"))
        self.assertEqual(text.count("## "), 2)
        files = core.git_run(self.origin, "ls-tree", "-r", "--name-only", "main").stdout.split()
        self.assertNotIn("CHANGELOG.md", files)

    def test_old_shared_changelog_is_kept_and_referenced(self):
        self.push("CHANGELOG.md", content="old")  # what versions before 0.5.0 wrote
        old_changelog = self.show("main:CHANGELOG.md")
        self.push("designs/Bracket/HISTORY.md", legacy="CHANGELOG.md", title="History: Bracket", content="new")
        self.assertEqual(self.show("main:CHANGELOG.md"), old_changelog)  # never rewritten or moved
        history = self.show("main:designs/Bracket/HISTORY.md")
        self.assertIn("Earlier pushes are listed in `CHANGELOG.md`", history)
        self.push("designs/Bracket/HISTORY.md", legacy="CHANGELOG.md", title="History: Bracket", content="newer")
        self.assertEqual(self.show("main:designs/Bracket/HISTORY.md").count("Earlier pushes"), 1)


if __name__ == "__main__":
    unittest.main()
