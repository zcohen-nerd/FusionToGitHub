"""Shared set-up for tests that drive the add-in through the simulated Fusion API.

Everything is isolated: settings, logs and repositories live in a temporary
folder; Git's system and global configuration are replaced by empty files
(see GitSandbox); tokens go to an in-memory store. Nothing here can touch the
developer's real settings, logs, credential vault or Git configuration.

Pushes run on a background thread (push_worker); ``push()`` presses OK and
then delivers the worker's messages on this thread, as Fusion's message loop
would, until the push has finished and its summary was shown. Every test
ends with no push running, no worker thread left, and no Fusion UI call made
from another thread.
"""

import json
import os
import threading
from unittest import mock

import _paths  # noqa: F401
import adsk
import adsk.core
import adsk.fusion
from test_core_identity_history import GitSandbox

import addin_logging
import Push_To_GitHub as addin
import push_worker
from credentials import MemoryCredentialStore
from settings_store import SettingsStore

DialogResults = adsk.core.DialogResults
PUSH_TIMEOUT = 60


def worker_threads():
    return [t for t in threading.enumerate() if t.name.startswith("PushToGitHub-") and t.is_alive()]


class AddinTestCase(GitSandbox):
    def setUp(self):
        super().setUp()
        self.app = adsk.core.Application.reset()
        self.ui = self.app.userInterface
        self.settings_path = os.path.join(self.base, "settings.json")
        self.repos_dir = os.path.join(self.base, "FusionGitRepos")
        self.creds = MemoryCredentialStore()
        for target, value in [
            ("app", self.app),
            ("ui", self.ui),
            ("CONFIG_PATH", self.settings_path),
            ("REPO_BASE_DIR", self.repos_dir),
            ("credential_store", self.creds),
            ("is_initialized", False),
            ("push_cmd_def", None),
            ("git_push_control", None),
            ("logger", None),
            ("bridge", None),
            ("owns_command", False),
        ]:
            patcher = mock.patch.object(addin, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        log_patch = mock.patch.object(addin_logging, "LOG_DIR", os.path.join(self.base, "logs"))
        log_patch.start()
        self.addCleanup(log_patch.stop)
        self.addCleanup(addin_logging.shutdown_logger)
        self.addCleanup(addin.handlers.clear)
        self.addCleanup(addin.dialog_handlers.clear)
        browser = mock.patch("webbrowser.open")
        self.opened_urls = browser.start()
        self.addCleanup(browser.stop)
        warned = mock.patch.object(addin, "_duplicate_warned", False)
        warned.start()
        self.addCleanup(warned.stop)
        self.addCleanup(self._check_background_work_ended)
        # Registered last, so it runs first: every question must have been
        # expected (scripted) and every scripted answer used.
        self.addCleanup(self._check_questions_were_scripted)

    def _check_background_work_ended(self):
        running = push_worker.is_busy()
        if addin.bridge is not None:
            addin.bridge.close(timeout=10)
        push_worker.shutdown_active(10)
        leftover = worker_threads()
        violations = self.app.thread_violations
        if running or leftover or violations:
            self.fail(f"push still running: {running}; worker threads left: {leftover}; "
                      f"Fusion UI used off the main thread: {violations}")

    def _check_questions_were_scripted(self):
        unscripted = list(self.ui.unscripted)
        unused = list(self.ui.answers)
        if unscripted or unused:
            self.fail(
                "Questions without a scripted answer: "
                + repr([q.splitlines()[0][:80] for q in unscripted])
                + f"; scripted answers never used: {unused}"
            )

    # -- helpers ---------------------------------------------------------------

    def seed(self, repositories, meta=None):
        store = SettingsStore(self.settings_path)
        store.load()
        for name, profile in repositories.items():
            store.add(name, profile)
        store.meta.update(meta or {})
        store.save()

    def settings(self):
        with open(self.settings_path, encoding="utf-8") as fh:
            return json.load(fh)

    def profile(self, name):
        return self.settings()["repositories"].get(name)

    def open_dialog(self):
        if not addin.is_initialized:
            addin.run(None)
        self.ui.messages.clear()
        self.ui.questions.clear()
        return self.ui.open_command(addin.CMD_ID)

    def answer(self, *results):
        self.ui.answers.extend(results)

    def push(self, command, timeout=PUSH_TIMEOUT):
        """Press OK, then run Fusion's "message loop" until the background push has finished."""
        args = adsk.core.press_ok(command)
        self.wait_for_push(timeout)
        return args

    def wait_for_push(self, timeout=PUSH_TIMEOUT):
        bridge = addin.bridge
        if bridge is None:
            return
        self.app.process_events(timeout=timeout, until=lambda: not bridge.busy)

    def design(self, name="Bracket", file_id="urn:adsk:bracket"):
        self.app.activeProduct = adsk.fusion.Design(name, file_id)
        return self.app.activeProduct

    def last_message(self):
        return self.ui.texts()[-1] if self.ui.messages else ""

    def remote_files(self, ref):
        proc = __import__("fusion_git_core").git_run(self.origin, "ls-tree", "-r", "--name-only", ref, check=False)
        return sorted(proc.stdout.splitlines())

    def remote_branches(self):
        proc = __import__("fusion_git_core").git_run(self.origin, "branch", "--format", "%(refname:short)")
        return proc.stdout.split()

    def work_profile(self, **extra):
        profile = {
            "path": self.work,
            "url": "https://github.com/acme/designs.git",
            "exportFormats": ["step"],
            "gitIdentity": {"name": "Ada Lovelace", "email": "ada@example.invalid"},
        }
        profile.update(extra)
        return profile
