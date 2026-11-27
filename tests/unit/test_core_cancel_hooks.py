"""Git core (S4): cancellation, hook isolation for token pushes, Git discovery, history notes."""

import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import _paths
from test_core_identity_history import GitSandbox, _UI

import fusion_git_core as core


def write_hook(repo_git_dir, name, body):
    path = os.path.join(repo_git_dir, "hooks", name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return path


class CancelTests(GitSandbox):
    def push(self, cancel, **kw):
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "a.step")], "note", "Part", ui,
            identity=self.identity, cancel=cancel, **kw,
        )
        return result, ui

    def cancel_after(self, seconds):
        token = threading.Event()
        timer = threading.Timer(seconds, token.set)
        timer.start()
        self.addCleanup(timer.cancel)
        return token

    def test_cancel_before_the_remote_accepts_reports_not_published(self):
        write_hook(self.origin, "pre-receive", "sleep 30\nexit 1")
        started = time.monotonic()
        result, ui = self.push(self.cancel_after(1.0))
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(result["cancelled"], True)
        self.assertFalse(result["published"])
        self.assertEqual(ui.errors, [])
        heads = core.git_run(self.origin, "branch", "--format", "%(refname:short)").stdout.split()
        self.assertFalse(any(h.startswith("fusion-export/") for h in heads), heads)

    def test_cancel_after_the_remote_accepted_reports_published(self):
        # post-receive runs after the branch was updated on the remote, while
        # the client is still waiting: cancelling then can't undo the push.
        first, ui = self.push(None)  # sets up the empty repository first
        self.assertTrue(first and not first.get("cancelled"), ui.errors)
        write_hook(self.origin, "post-receive", "sleep 30")
        result, ui = self.push(self.cancel_after(1.5))
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["published"], result)
        tip = core.git_run(self.origin, "rev-parse", result["branch"]).stdout.strip()
        self.assertEqual(tip, result["commit"])

    def test_cancel_scope_is_per_thread_and_restored(self):
        token = threading.Event()
        token.set()
        with core.cancel_scope(token):
            with self.assertRaises(core.GitCancelled):
                core.git_run(self.work, "-c", "alias.wait=!sleep 5", "wait")
        # Outside the scope the same command isn't cancelled (it just runs).
        self.assertIsNone(getattr(core._CANCEL_SCOPE, "token", None))

    def test_cancel_while_setting_up_an_empty_repository_is_reported(self):
        write_hook(self.origin, "post-receive", "sleep 30")
        result, ui = self.push(self.cancel_after(1.5))
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["published"])  # the export itself was not sent
        self.assertTrue(result["repository_initialized"], result)

    def test_without_a_token_nothing_changes(self):
        result, ui = self.push(None)
        self.assertTrue(result and not result.get("cancelled"), ui.errors)


class HookIsolationTests(GitSandbox):
    """R-21: no repository hook runs inside a git process that holds the token."""

    def test_hooks_do_not_run_when_a_token_is_passed(self):
        marker = os.path.join(self.base, "hook-ran.txt")
        write_hook(os.path.join(self.work, ".git"), "pre-push", f'env > "{marker.replace(chr(92), "/")}"')
        core.git_run(self.work, "-c", "commit.gpgSign=false", "commit", "--allow-empty", "-m", "x",
                     env={"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@b.invalid",
                          "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@b.invalid"})
        empty = tempfile.mkdtemp(prefix="ftg_nohooks_")
        self.addCleanup(_paths.force_rmtree, empty)
        auth = core.GitAuth(host="git.example.invalid", token="ghp_" + "q" * 36, hooks_dir=empty)
        core.git_run(self.work, "push", "origin", "HEAD:refs/heads/with-token", auth=auth, network=True)
        self.assertFalse(os.path.exists(marker), "a hook ran while the token was in the environment")
        core.git_run(self.work, "push", "origin", "HEAD:refs/heads/without-token", network=True)
        self.assertTrue(os.path.exists(marker), "control: the hook should run without a token")
        with open(marker, encoding="utf-8", errors="replace") as fh:
            self.assertNotIn("FUSION_GIT_TOKEN", fh.read())

    def test_token_config_includes_the_empty_hooks_folder(self):
        auth = core.GitAuth(host="github.com", token="t" * 40, hooks_dir="/tmp/empty")
        self.assertIn("core.hooksPath=/tmp/empty", auth.config)
        self.assertNotIn("t" * 40, repr(auth))


class DiscoveryTests(unittest.TestCase):
    def test_override_wins_when_it_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as fh:
            fake = fh.name
        self.addCleanup(os.remove, fake)
        with mock.patch.dict(os.environ, {core.GIT_OVERRIDE_ENV: fake}):
            self.assertEqual(core.find_git(), fake)
        with mock.patch.dict(os.environ, {core.GIT_OVERRIDE_ENV: fake + ".missing"}):
            self.assertNotEqual(core.find_git(), fake + ".missing")

    def test_macos_prefers_real_installs_over_the_usr_bin_placeholder(self):
        with mock.patch.object(core, "IS_WINDOWS", False), \
                mock.patch.dict(os.environ, {core.GIT_OVERRIDE_ENV: ""}), \
                mock.patch.object(core.os.path, "isfile", lambda p: p in ("/opt/homebrew/bin/git", "/usr/bin/git")), \
                mock.patch.object(core.shutil, "which", lambda name: "/usr/bin/git"):
            self.assertEqual(core.find_git(), "/opt/homebrew/bin/git")
        with mock.patch.object(core, "IS_WINDOWS", False), \
                mock.patch.dict(os.environ, {core.GIT_OVERRIDE_ENV: ""}), \
                mock.patch.object(core.os.path, "isfile", lambda p: False), \
                mock.patch.object(core.shutil, "which", lambda name: None):
            self.assertEqual(core.find_git(), "git")

    def test_windows_candidates_cover_common_installs(self):
        env = {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
        with mock.patch.object(core, "IS_WINDOWS", True), mock.patch.dict(os.environ, env, clear=False):
            joined = " | ".join(core.git_candidates())
        self.assertIn(os.path.join(r"C:\Program Files", "Git", "cmd", "git.exe"), joined)
        self.assertIn(os.path.join(r"C:\Users\u\AppData\Local", "Programs", "Git", "cmd", "git.exe"), joined)


class HistoryNoteTests(GitSandbox):
    def test_notes_are_recorded_in_the_history_entry(self):
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "Part/a.step")], "note", "Part", ui,
            mode=core.MODE_SINGLE, identity=self.identity, history_file="Part/HISTORY.md",
            history_notes=["Contains 2 linked components; this backup may not be self-contained."],
        )
        self.assertTrue(result, ui.errors)
        history = self.show("main:Part/HISTORY.md")
        self.assertIn("- **Note:** Contains 2 linked components", history)


if __name__ == "__main__":
    unittest.main()
