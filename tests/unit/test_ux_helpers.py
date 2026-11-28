"""S5 helpers without Fusion: error catalog, GitHub links, Check My Setup, history modes, icons."""

import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _paths

import error_catalog as ec
import fusion_git_core as core
import github_links as gl
import setup_check as sc
from fusion_export import design_version_text, format_from_choice
from push_controller import DEFAULT_COMMIT_TEMPLATE, compose_commit_message, new_profile_settings
from settings_store import history_mode, validate_profile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ErrorCatalogTests(unittest.TestCase):
    RAW = {
        "auth": "git push failed:\nremote: Invalid username or password.\nfatal: Authentication failed for 'https://github.com/a/b.git/'",
        "not_found": "git ls-remote failed:\nremote: Repository not found.\nfatal: repository 'https://github.com/a/b.git/' not found",
        "network": "fatal: unable to access 'https://github.com/a/b.git/': Could not resolve host: github.com",
        "timeout": "git push took longer than 600 seconds and was stopped. Check your internet connection",
        "lock": "fatal: Unable to create 'C:/repo/.git/index.lock': File exists.",
        "too_large": "remote: error: File big.stl is 120.00 MB; this exceeds GitHub's file size limit of 100.00 MB\nremote: error: GH001: Large files detected.",
        "protected_branch": "remote: error: GH006: Protected branch update failed for refs/heads/main.",
        "tls": "fatal: unable to access 'https://github.com/a/b.git/': SSL certificate problem: unable to get local issuer certificate",
        "disk_full": "error: unable to write file: No space left on device",
        "identity": "Please tell me who you are.",
    }

    def test_each_known_failure_gets_a_plain_first_line_and_a_next_step(self):
        for key, raw in self.RAW.items():
            with self.subTest(key=key):
                found = ec.classify(raw)
                self.assertIsNotNone(found)
                self.assertEqual(found.key, key)
                text = ec.explain(raw)
                first = text.splitlines()[0]
                self.assertEqual(first, found.headline)
                self.assertNotIn("fatal:", first)
                self.assertIn(found.next_step, text)
                self.assertIn("Technical details:", text)

    def test_messages_written_for_people_are_unchanged(self):
        text = "Nothing was pushed because these exports failed:\n • Bracket.step is empty"
        self.assertEqual(ec.explain(text), text)

    def test_unknown_git_output_still_gets_a_plain_first_line(self):
        text = ec.explain("git push failed:\nfatal: something nobody has seen before")
        self.assertTrue(text.startswith("The backup didn't complete because Git reported an error."))
        self.assertIn("something nobody has seen before", text)

    def test_nothing_changed_is_said_when_known(self):
        text = ec.explain(self.RAW["auth"], nothing_changed=True)
        self.assertIn("Nothing was pushed.", text.splitlines()[0])

    def test_details_are_bounded(self):
        raw = "fatal: x\n" + "\n".join(f"line {i}" for i in range(100))
        text = ec.explain(raw)
        self.assertLess(len(text), ec.DETAIL_MAX_CHARS + 600)
        self.assertIn("…", text)

    def test_unexpected_errors_have_no_traceback(self):
        try:
            raise KeyError("designs")
        except KeyError as exc:
            text = ec.unexpected_error("starting the backup", exc)
        self.assertTrue(text.startswith("Something went wrong while starting the backup. Nothing was pushed."))
        self.assertIn("KeyError: 'designs'", text)
        self.assertFalse(ec.contains_traceback(text))


class GitHubLinkTests(unittest.TestCase):
    def test_repository_pages(self):
        cases = {
            "https://github.com/acme/designs.git": "https://github.com/acme/designs",
            "https://github.com/acme/designs": "https://github.com/acme/designs",
            "git@github.com:acme/designs.git": "https://github.com/acme/designs",
            "ssh://git@github.com/acme/designs.git": "https://github.com/acme/designs",
            "https://GitHub.com/Acme/Designs.git/": "https://github.com/Acme/Designs",
            "https://git.example.invalid:8443/team/cad.git": "https://git.example.invalid:8443/team/cad",
            "https://user:secret@github.com/acme/designs.git": None,
            "file:///C:/repos/designs.git": None,
            "C:\\repos\\designs": None,
            "https://github.com/acme": None,
            "": None,
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(gl.web_repository_url(remote), expected)

    def test_folder_links_point_at_the_branch_and_folder_on_github_only(self):
        self.assertEqual(
            gl.folder_url("https://github.com/acme/designs.git", "main", "designs/Bracket (2)"),
            "https://github.com/acme/designs/tree/main/designs/Bracket%20%282%29",
        )
        self.assertEqual(
            gl.folder_url("https://github.com/acme/designs.git", "fusion-export/Arm-1", "Arm"),
            "https://github.com/acme/designs/tree/fusion-export/Arm-1/Arm",
        )
        self.assertEqual(gl.folder_url("https://github.com/acme/designs.git", "main", ""),
                         "https://github.com/acme/designs/tree/main")
        # Other servers lay out their pages differently: the repository page only.
        self.assertEqual(gl.folder_url("https://gitlab.example.invalid/a/b.git", "main", "x"),
                         "https://gitlab.example.invalid/a/b")
        self.assertIsNone(gl.folder_url("C:/local/bare.git", "main", "x"))

    def test_copy_uses_the_system_tool_and_reports_failure(self):
        with mock.patch.object(gl.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(gl.copy_to_clipboard("https://github.com/a/b"))
        command = run.call_args[0][0]
        self.assertEqual(command, ["clip"] if os.name == "nt" else ["pbcopy"])
        with mock.patch.object(gl.subprocess, "run", side_effect=OSError("missing")):
            self.assertFalse(gl.copy_to_clipboard("https://github.com/a/b"))
        self.assertFalse(gl.copy_to_clipboard(""))


class FakeGit:
    """Just enough of fusion_git_core for setup_check's local checks."""

    GitError = core.GitError
    GIT_EXE = "/usr/bin/git"
    redact_secrets = staticmethod(core.redact_secrets)
    _repository_key = staticmethod(core._repository_key)

    def __init__(self, version="git version 2.47.1.windows.1", config=None):
        self.version = version
        self.config = config or {}

    def git_run(self, repo_path, *args, check=True, timeout=None):
        if args == ("--version",):
            if self.version is None:
                raise OSError("not found")
            return SimpleNamespace(returncode=0, stdout=self.version, stderr="")
        key = args[-1]
        value = self.config.get(key)
        return SimpleNamespace(returncode=0 if value else 1, stdout=value or "", stderr="")


class SetupCheckTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ftg_setup_")
        self.addCleanup(_paths.force_rmtree, self.dir)
        os.makedirs(os.path.join(self.dir, ".git"))

    def test_git_versions(self):
        self.assertEqual(sc.parse_git_version("git version 2.47.1.windows.1"), (2, 47, 1))
        self.assertEqual(sc.check_git(FakeGit()).status, sc.OK)
        old = sc.check_git(FakeGit("git version 2.20.0"))
        self.assertEqual(old.status, sc.WARN)
        self.assertIn("2.30", old.detail)
        missing = sc.check_git(FakeGit(None))
        self.assertEqual(missing.status, sc.PROBLEM)
        self.assertIn("git-scm.com", missing.next_step)
        # Without Git nothing else can be checked.
        self.assertEqual(len(sc.local_checks(None, None, git=FakeGit(None))), 1)

    def test_sign_in_helpers(self):
        gcm = FakeGit(config={"credential.helper": "manager"})
        self.assertEqual(sc.check_sign_in(gcm).status, sc.OK)
        none = FakeGit()
        self.assertEqual(sc.check_sign_in(none, is_windows=True).status, sc.WARN)
        keychain = FakeGit(config={"credential.helper": "osxkeychain"})
        self.assertEqual(sc.check_sign_in(keychain, is_windows=False).status, sc.WARN)
        self.assertEqual(sc.check_sign_in(none, {"useStoredPat": True}, token_stored=True).status, sc.OK)
        self.assertEqual(sc.check_sign_in(none, {"useStoredPat": True}, token_stored=False).status, sc.PROBLEM)

    def test_identity(self):
        self.assertEqual(sc.check_identity(FakeGit(), {"gitIdentity": {"name": "A", "email": "a@x"}}).status, sc.OK)
        self.assertEqual(sc.check_identity(FakeGit()).status, sc.INFO)  # asked once at the first backup

    def test_repository_folder_and_address(self):
        git = FakeGit(config={"remote.origin.url": "https://github.com/acme/designs.git"})
        profile = {"path": self.dir, "url": "https://github.com/acme/designs"}
        self.assertEqual([c.status for c in sc.check_repository(git, "Designs", profile)], [sc.OK])
        other = dict(profile, url="https://github.com/acme/other.git")
        self.assertIn(sc.WARN, [c.status for c in sc.check_repository(git, "Designs", other)])
        missing = sc.check_repository(git, "Designs", {"path": os.path.join(self.dir, "nope")})
        self.assertEqual(missing[0].status, sc.PROBLEM)
        no_origin = sc.check_repository(FakeGit(), "Designs", profile)
        self.assertIn(sc.PROBLEM, [c.status for c in no_origin])

    def test_connection_results(self):
        self.assertEqual(sc.connection_check({"ok": True, "default_branch": "main"}).status, sc.OK)
        self.assertIn("empty", sc.connection_check({"ok": True, "empty": True}).title)
        auth = sc.connection_check({"ok": False, "error": "fatal: Authentication failed for 'https://github.com/a/b'"})
        self.assertEqual(auth.status, sc.PROBLEM)
        self.assertEqual(auth.title, ec.classify("Authentication failed").headline)
        self.assertEqual(sc.connection_check({"cancelled": True}).status, sc.INFO)

    def test_report_uses_words_not_only_symbols(self):
        text = sc.format_report([sc.Check(sc.OK, "Git 2.47 is installed."),
                                 sc.Check(sc.PROBLEM, "No folder.", "C:/x", "Choose it.")])
        self.assertIn("1 problem to fix before backing up.", text)
        self.assertIn("[OK] Git 2.47 is installed.", text)
        self.assertIn("[Problem] No folder.", text)
        self.assertIn("    Next: Choose it.", text)
        self.assertIn("Everything needed", sc.format_report([sc.Check(sc.OK, "x")]))

    def test_connection_test_against_a_local_repository(self):
        # A real, read-only ls-remote against a local bare repository.
        bare = os.path.join(self.dir, "origin.git")
        work = os.path.join(self.dir, "work")
        core.git_run(None, "init", "--bare", bare)
        core.git_run(None, "init", work)
        core.git_run(work, "remote", "add", "origin", bare)
        result = sc.ConnectionTest(work).execute(None, None)
        self.assertEqual(result["kind"], "setup_check")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["empty"])
        broken = core.check_connection(os.path.join(self.dir, "nope"))
        self.assertFalse(broken["ok"])


class HistoryModeAndMessageTests(unittest.TestCase):
    def test_new_profiles_keep_one_history_in_designs(self):
        settings = new_profile_settings()
        self.assertEqual(settings["historyMode"], core.MODE_SINGLE)
        self.assertEqual(settings["exportSubfolder"], "designs")
        self.assertEqual(history_mode(settings), core.MODE_SINGLE)

    def test_profiles_from_before_0_7_keep_snapshot_branches(self):
        self.assertEqual(history_mode({"path": "x"}), core.MODE_SNAPSHOT)
        self.assertEqual(history_mode({"historyMode": "bogus"}), core.MODE_SNAPSHOT)
        self.assertIn("'historyMode' is not 'single' or 'snapshot'",
                      validate_profile({"path": "x", "historyMode": "bogus"}))
        self.assertIn("'targetBranch' is not text", validate_profile({"path": "x", "targetBranch": 3}))

    def test_commit_messages(self):
        self.assertEqual(compose_commit_message(DEFAULT_COMMIT_TEMPLATE, "holes 5 mm"), "{filename}: holes 5 mm")
        # A template saved before 0.7.0 has no {message}: the typed text is the message.
        self.assertEqual(compose_commit_message("Design update: {filename}", "holes"), "holes")
        self.assertEqual(compose_commit_message("Design update: {filename}", ""), "Design update: {filename}")
        self.assertEqual(compose_commit_message("", ""), "{filename}: Design update")
        self.assertEqual(compose_commit_message("{message}", "two\nlines"), "two lines")

    def test_branch_name_problems(self):
        for good in ("main", "fusion-backups", "team/cad", "v1.2"):
            self.assertEqual(core.branch_name_problem(good), "", good)
        for bad in ("", "-x", "a b", "a..b", "a~1", "x/", "x.lock", ".x", "a/.b", "a\\b", "a:b", "@", "a@{1"):
            self.assertNotEqual(core.branch_name_problem(bad), "", bad)
        # Agrees with git itself for these.
        for name in ("main", "a..b", "x.lock", "team/cad"):
            self.assertEqual(core.is_valid_branch_name(name), core.branch_name_problem(name) == "", name)


class DesignVersionTests(unittest.TestCase):
    def design(self, data_file, modified=False):
        return SimpleNamespace(parentDocument=SimpleNamespace(dataFile=data_file, isModified=modified))

    def test_version_texts(self):
        self.assertEqual(design_version_text(self.design(SimpleNamespace(versionNumber=12))), "v12")
        self.assertEqual(design_version_text(self.design(SimpleNamespace(versionNumber=12), True)),
                         "v12 with unsaved changes")
        self.assertEqual(design_version_text(self.design(None)), "not saved yet")
        self.assertEqual(design_version_text(self.design(SimpleNamespace())), "saved")
        self.assertEqual(design_version_text(object()), "")

    def test_format_labels_map_back_to_codes(self):
        self.assertEqual(format_from_choice("STL (.stl, millimetres): for 3D printing"), "stl")
        self.assertEqual(format_from_choice("step"), "step")


class IconTests(unittest.TestCase):
    def test_committed_icons_match_the_generator(self):
        # Rendering the 512 px icon takes a few seconds; the others are quick.
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_icons.py"), "--check"],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_icons_have_no_third_party_marks_and_the_right_sizes(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        try:
            import make_icons
        finally:
            sys.path.remove(os.path.join(ROOT, "scripts"))
        for path, (size, _) in make_icons.OUTPUTS.items():
            with open(os.path.join(ROOT, path), "rb") as fh:
                data = fh.read()
            if size == "svg":
                text = data.decode("utf-8")
                self.assertNotIn("<image", text)  # vector only, no embedded raster
                self.assertNotIn("base64", text)
            else:
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
                self.assertEqual((width, height), (size, size), path)


if __name__ == "__main__":
    unittest.main()
