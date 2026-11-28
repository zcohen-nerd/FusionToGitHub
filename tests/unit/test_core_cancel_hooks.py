"""Git core (S4): cancellation, hook isolation for token pushes, Git discovery, history notes."""

import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
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

    def hook_then_cancel(self, hook, only_refs=None):
        """Install a remote *hook* that signals, then waits; cancel once it signals.

        Cancelling on the hook's signal (not after a fixed delay) makes the
        moment of cancellation deterministic on slow machines. With
        *only_refs* (a shell pattern), only pushes of matching refs wait.
        """
        marker = os.path.join(self.base, f"{hook}-started")
        stall = f'touch "{marker.replace(chr(92), "/")}"\nsleep 30\nexit 1'
        if only_refs:
            stall = (f'while read old new ref; do case "$ref" in {only_refs}) '
                     f'touch "{marker.replace(chr(92), "/")}"; sleep 30; exit 1;; esac; done\nexit 0')
        write_hook(self.origin, hook, stall)
        token = threading.Event()
        stop = threading.Event()

        def watch():
            deadline = time.monotonic() + 60
            while not stop.is_set() and time.monotonic() < deadline:
                if os.path.exists(marker):
                    token.set()
                    return
                time.sleep(0.05)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        self.addCleanup(watcher.join, 5)
        self.addCleanup(stop.set)
        return token

    def test_cancel_before_the_remote_accepts_reports_not_published(self):
        started = time.monotonic()
        result, ui = self.push(self.hook_then_cancel("pre-receive"))
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
        result, ui = self.push(self.hook_then_cancel("post-receive"))
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
        result, ui = self.push(self.hook_then_cancel("post-receive"))
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["published"])  # the export itself was not sent
        self.assertTrue(result["repository_initialized"], result)

    def test_cancel_after_the_empty_repository_was_set_up_still_says_so(self):
        # Found in review: the first commit of an empty repository went
        # through, then the export push was cancelled; the result said
        # "nothing was pushed" although GitHub now had that first commit.
        # pre-receive: the export branch is held *before* GitHub accepts it.
        result, ui = self.push(self.hook_then_cancel("pre-receive", only_refs="refs/heads/fusion-export/*"))
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["published"], result)
        self.assertTrue(result["repository_initialized"], result)
        heads = core.git_run(self.origin, "branch", "--format", "%(refname:short)").stdout.split()
        self.assertIn(core.BOOTSTRAP_BRANCH, heads)

    def test_without_a_token_nothing_changes(self):
        result, ui = self.push(None)
        self.assertTrue(result and not result.get("cancelled"), ui.errors)


class _LocalOriginAuth(core.GitAuth):
    """Test only: the sandbox's origin is a local folder, which real token
    pushes refuse (https only). Allowing the file transport here isolates the
    hooks behaviour being tested."""

    @property
    def env(self):
        return {**super().env, "GIT_ALLOW_PROTOCOL": "https:file"}


FAKE_TOKEN = "ghp_" + "q" * 36
# Before any test patches it (GitSandbox points it at a temporary folder).
REAL_CREDENTIALS_ROOT = core._credentials_root


class HookIsolationTests(GitSandbox):
    """R-21: no repository hook runs inside a git process that holds the token."""

    def no_hooks(self):
        empty = tempfile.mkdtemp(prefix="ftg_nohooks_")
        self.addCleanup(_paths.force_rmtree, empty)
        return empty

    def commit(self):
        core.git_run(self.work, "-c", "commit.gpgSign=false", "commit", "--allow-empty", "-m", "x",
                     env={"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@b.invalid",
                          "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@b.invalid"})

    def test_hooks_do_not_run_when_a_token_is_passed(self):
        marker = os.path.join(self.base, "hook-ran.txt")
        write_hook(os.path.join(self.work, ".git"), "pre-push", f'env > "{marker.replace(chr(92), "/")}"')
        self.commit()
        empty = tempfile.mkdtemp(prefix="ftg_nohooks_")
        self.addCleanup(_paths.force_rmtree, empty)
        auth = _LocalOriginAuth(host="git.example.invalid", token=FAKE_TOKEN, hooks_dir=empty)
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
        for item in ("core.askPass=", "fetch.recurseSubmodules=false", "push.recurseSubmodules=no",
                     "submodule.recurse=false"):
            self.assertIn(item, auth.config)

    def test_repository_config_cannot_start_a_program_that_sees_the_token(self):
        # A repository can rewrite its address to "ext::<command>" and allow
        # that transport in its own config. Without a token the command runs
        # (the control); with the token, only https may run, so it never does.
        marker = os.path.join(self.base, "ext-ran.txt").replace("\\", "/")
        rewrite = f"url.ext::sh -c env>{marker} %S.insteadOf"
        core.git_run(self.work, "remote", "set-url", "origin", "https://git.example.invalid/o/r.git")
        core.git_run(self.work, "config", rewrite, "https://git.example.invalid/")
        core.git_run(self.work, "config", "protocol.ext.allow", "always")
        auth = replace(core.token_auth("https://git.example.invalid/o/r.git", FAKE_TOKEN), hooks_dir=self.no_hooks())
        for args in (("ls-remote", "origin"), ("fetch", "origin"), ("push", "origin", "HEAD:refs/heads/x")):
            result = core.git_run(self.work, *args, auth=auth, network=True, check=False)
            self.assertNotEqual(result.returncode, 0, args)
            self.assertFalse(os.path.exists(marker), f"{args[0]}: a configured program ran with the token")
            self.assertNotIn(FAKE_TOKEN, result.stderr + result.stdout)
        core.git_run(self.work, "ls-remote", "origin", network=True, check=False)
        self.assertTrue(os.path.exists(marker), "control: without a token the rewrite should take effect")

    def test_a_token_is_never_given_to_git_with_hooks_enabled(self):
        auth = core.GitAuth(host="git.example.invalid", token=FAKE_TOKEN)  # no empty hooks folder
        with self.assertRaises(core.GitError):
            core.git_run(self.work, "status", auth=auth)

    def set_config(self, *pairs, repo=None):
        for key, value in pairs:
            core.git_run(repo or self.work, "config", key, value)

    def test_repository_network_settings_that_could_divert_the_token_are_found(self):
        # Found in the S4 security review: a repository's own http.proxy plus
        # http.sslVerify=false sent the token to a TLS-terminating proxy, and
        # url-specific keys beat any "-c" override, so they are refused.
        included = os.path.join(self.base, "included.gitconfig")
        with open(included, "w", encoding="utf-8") as fh:
            fh.write("[http]\n\tsslCAInfo = /tmp/attacker-ca.pem\n")
        self.set_config(
            ("http.https://git.example.invalid/.proxy", "http://127.0.0.1:9"),
            ("http.sslVerify", "false"),
            ("remote.origin.proxy", "http://127.0.0.1:9"),
            ("http.postBuffer", "524288000"),  # harmless, and common
            ("include.path", included.replace("\\", "/")),
        )
        found = {key.lower() for key in core.risky_local_network_config(self.work)}
        self.assertEqual(found, {"http.https://git.example.invalid/.proxy", "http.sslverify",
                                 "remote.origin.proxy", "http.sslcainfo"})
        self.assertNotIn("http.postbuffer", found)

    def test_harmless_repository_settings_are_not_flagged(self):
        self.set_config(("http.postBuffer", "524288000"), ("remote.origin.prune", "true"))
        self.assertEqual(core.risky_local_network_config(self.work), [])

    def test_a_token_push_is_refused_before_contacting_the_server(self):
        core.git_run(self.work, "remote", "set-url", "origin", "https://git.example.invalid/o/r.git")
        self.set_config(("http.proxy", "http://127.0.0.1:9"))
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "a.step")], "note", "Part", ui,
            identity=self.identity, pat_credentials={"token": FAKE_TOKEN},
        )
        self.assertIsNone(result)
        text = "\n".join(ui.errors)
        self.assertIn("won't send your stored token", text)
        self.assertIn("http.proxy", text)
        self.assertNotIn(FAKE_TOKEN, text)

    def test_http_traces_from_the_users_environment_are_off_and_redacted(self):
        # R-21 investigation: with GIT_TRACE_CURL / GIT_CURL_VERBOSE and
        # GIT_TRACE_REDACT=0 in the user's environment, git wrote the
        # Authorization header (the token in base64) to a file and to stderr,
        # and from stderr into the add-in's error message.
        auth = core.GitAuth(host="git.example.invalid", token=FAKE_TOKEN, hooks_dir=self.no_hooks())
        user_env = {"GIT_TRACE_CURL": "/tmp/x", "GIT_CURL_VERBOSE": "1", "GIT_TRACE_REDACT": "0"}
        with mock.patch.dict(os.environ, user_env):
            seen = core.git_run(self.work, "-c", "alias.showenv=!env", "showenv", auth=auth).stdout
        self.assertIn("GIT_TRACE_REDACT=1", seen)
        self.assertNotIn("GIT_TRACE_CURL=", seen)
        self.assertNotIn("GIT_CURL_VERBOSE=", seen)
        basic = core.token_secrets(FAKE_TOKEN)[1]
        with self.assertRaises(core.GitError) as raised:
            core.git_run(self.work, "-c", f"alias.leak=!echo 'Authorization: Basic {basic}' >&2; exit 1", "leak",
                         auth=auth)
        self.assertNotIn(basic, str(raised.exception))
        self.assertNotIn(FAKE_TOKEN, str(raised.exception))

    def test_a_push_to_another_repository_on_the_same_server_is_refused(self):
        # R-21 investigation: remote.origin.pushurl (or url.*.insteadOf) sent
        # the synthetic token, and the design, to another repository on the
        # same host, past the host check.
        url = "https://git.example.invalid/acme/designs.git"
        core.git_run(self.work, "remote", "set-url", "origin", url)
        self.assertEqual(core.token_destination_problem(self.work), "")
        self.assertEqual(core.token_destination_problem(self.work, "https://GIT.example.invalid/Acme/designs/"), "")
        self.assertIn("won't send your stored token",
                      core.token_destination_problem(self.work, "https://git.example.invalid/acme/other.git"))
        self.set_config(("remote.origin.pushurl", "https://git.example.invalid/attacker/loot.git"))
        self.assertIn("attacker/loot", core.token_destination_problem(self.work))
        core.git_run(self.work, "config", "--unset", "remote.origin.pushurl")
        self.set_config(("url.https://git.example.invalid/attacker/.pushInsteadOf", "https://git.example.invalid/acme/"))
        self.assertIn("attacker", core.token_destination_problem(self.work))
        ui = _UI()
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "a.step")], "note", "Part", ui,
            identity=self.identity, pat_credentials={"token": FAKE_TOKEN},
        )
        self.assertIsNone(result)
        self.assertIn("won't send your stored token", "\n".join(ui.errors))

    def test_askpass_programs_are_not_inherited_by_token_processes(self):
        auth = core.GitAuth(host="git.example.invalid", token=FAKE_TOKEN, hooks_dir=self.no_hooks())
        with mock.patch.dict(os.environ, {"GIT_ASKPASS": "/bin/evil", "SSH_ASKPASS": "/bin/evil"}):
            seen = core.git_run(self.work, "-c", "alias.showenv=!env", "showenv", auth=auth).stdout
            control = core.git_run(self.work, "-c", "alias.showenv=!env", "showenv").stdout
        self.assertNotIn("ASKPASS=/bin/evil", seen)
        self.assertIn("GIT_ALLOW_PROTOCOL=https", seen)
        self.assertIn("GIT_ASKPASS=/bin/evil", control)


class TokenOutOfEnvironmentTests(GitSandbox):
    """R-21 E4: the token is never in a git process's environment."""

    def auth(self, **extra):
        empty = tempfile.mkdtemp(prefix="ftg_nohooks_")
        self.addCleanup(_paths.force_rmtree, empty)
        return core.GitAuth(host="git.example.invalid", token=FAKE_TOKEN, hooks_dir=empty, **extra)

    def credential_dirs(self):
        return set(os.listdir(core._credentials_root()))

    def test_git_processes_get_a_file_path_not_the_token(self):
        before = self.credential_dirs()
        with mock.patch.dict(os.environ, {"FUSION_GIT_TOKEN": "inherited", "FUSION_GIT_USERNAME": "x"}):
            seen = core.git_run(self.work, "-c", "alias.showenv=!env", "showenv", auth=self.auth()).stdout
        self.assertNotIn(FAKE_TOKEN, seen)
        self.assertNotIn("FUSION_GIT_TOKEN=", seen)  # inherited ones are removed too
        self.assertNotIn("FUSION_GIT_USERNAME=", seen)
        path = next(line.split("=", 1)[1] for line in seen.splitlines()
                    if line.startswith(core.CREDENTIALS_FILE_ENV + "="))
        self.assertFalse(os.path.exists(path), "the credential file outlived the git command")
        self.assertEqual(self.credential_dirs(), before)
        self.assertEqual(core._credential_cleanup_failures, [])

    def test_the_helper_answers_from_the_file_for_its_host_only(self):
        answer = core.git_run(self.work, "credential", "fill", auth=self.auth(username="octocat"),
                              input_text="protocol=https\nhost=git.example.invalid\n\n").stdout
        self.assertIn(f"password={FAKE_TOKEN}", answer)
        self.assertIn("username=octocat", answer)
        other = core.git_run(self.work, "credential", "fill", auth=self.auth(), check=False,
                             input_text="protocol=https\nhost=evil.example.invalid\n\n").stdout
        self.assertNotIn(FAKE_TOKEN, other)

    def test_a_temporary_folder_with_spaces_works(self):
        spaced = os.path.join(self.base, "Temp With Spaces")
        os.makedirs(spaced)
        auth = self.auth()
        with mock.patch.object(core, "_credentials_root", lambda: spaced):
            answer = core.git_run(self.work, "credential", "fill", auth=auth,
                                  input_text="protocol=https\nhost=git.example.invalid\n\n").stdout
        self.assertIn(f"password={FAKE_TOKEN}", answer)
        self.assertEqual(os.listdir(spaced), [])

    def test_the_file_is_removed_when_git_fails_and_private_while_it_exists(self):
        before = self.credential_dirs()
        probe = os.path.join(self.base, "mode.txt").replace("\\", "/")
        with self.assertRaises(core.GitError):
            core.git_run(self.work, "-c", f'alias.fail=!ls -l "$FUSION_GIT_CREDENTIALS" > "{probe}"; exit 3',
                         "fail", auth=self.auth())
        self.assertEqual(self.credential_dirs(), before)
        with open(probe, encoding="utf-8") as fh:
            listing = fh.read()
        if os.name != "nt":
            self.assertTrue(listing.startswith("-rw-------"), listing)
        self.assertIn("credential", listing)

    def test_a_token_or_username_with_a_line_break_or_nul_is_refused(self):
        for token, username in (("abc\npassword=evil", ""), ("abc\rdef", ""), ("abc\0def", ""),
                                (FAKE_TOKEN, "me\rhost=evil"), (FAKE_TOKEN, "me\0")):
            auth = core.GitAuth(host="git.example.invalid", token=token, username=username, hooks_dir=self.base)
            with self.assertRaises(core.GitError):
                core.git_run(self.work, "status", auth=auth)

    def test_windows_keeps_credentials_in_local_app_data_not_temp(self):
        # S5 security review: %TEMP% can be redirected to a shared folder.
        local = os.path.join(self.base, "LocalAppData")
        os.makedirs(local)
        with mock.patch.object(core, "IS_WINDOWS", True), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": local, "TEMP": self.base, "TMP": self.base}):
            self.assertEqual(REAL_CREDENTIALS_ROOT(), os.path.join(local, "PushToGitHub", "credentials"))
        self.assertTrue(os.path.isdir(os.path.join(local, "PushToGitHub", "credentials")))

    def test_the_file_is_overwritten_before_it_is_deleted(self):
        folder = tempfile.mkdtemp(prefix=core._CREDENTIALS_DIR_PREFIX, dir=core._credentials_root())
        path = os.path.join(folder, "credential")
        with open(path, "wb") as fh:
            fh.write(b"password=" + FAKE_TOKEN.encode())
        written = []
        real_open = open

        def spy(file, mode="r", *args, **kwargs):
            handle = real_open(file, mode, *args, **kwargs)
            if file == path and "+" in mode:
                written.append(file)
            return handle

        with mock.patch("builtins.open", spy):
            self.assertTrue(core._remove_credentials(folder))
        self.assertEqual(written, [path])
        self.assertFalse(os.path.exists(folder))
        self.assertFalse(core._is_plain_dir(path))  # a file is never treated as a credential folder

    def test_stale_folders_from_a_killed_process_are_swept(self):
        stale = tempfile.mkdtemp(prefix=core._CREDENTIALS_DIR_PREFIX, dir=core._credentials_root())
        fresh = tempfile.mkdtemp(prefix=core._CREDENTIALS_DIR_PREFIX, dir=core._credentials_root())
        # Younger than the longest a git command can run (10 minutes): kept.
        recent = time.time() - core.TIMEOUTS["network"] - 60
        os.utime(fresh, (recent, recent))
        old = time.time() - core._STALE_CREDENTIALS_SECONDS - 60
        os.utime(stale, (old, old))
        with mock.patch.object(core, "_last_sweep", 0.0):
            core.git_run(self.work, "status", auth=self.auth())
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(fresh))


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


class SingleLineTests(GitSandbox):
    """Design and component names can't add lines to HISTORY.md or the commit message."""

    def test_single_line(self):
        self.assertEqual(core.single_line("Arm\n- **Note:** fake\r\nline"), "Arm - **Note:** fake line")
        self.assertEqual(core.single_line("A B C\x85D\x00E"), "A B C D E")
        self.assertEqual(core.single_line("Bra‮ck​et"), "Bracket")

    def test_a_multi_line_design_name_stays_on_one_line_in_history_and_commit(self):
        ui = _UI()
        evil = "Part\n- **Note:** forged line\n\nSigned-off-by: Someone <x@example.invalid>"
        result = core.push_export(
            self.work, [(self.export("a.step", "A"), "Part/a.step")], "Update {filename}", evil, ui,
            identity=self.identity, history_file="Part/HISTORY.md", history_title=evil,
            history_notes=["Contains 1 linked component (Bolt\nM5)"],
        )
        self.assertTrue(result and not result.get("cancelled"), ui.errors)
        message = core.git_run(self.origin, "log", "-1", "--format=%B", result["branch"]).stdout
        history = core.git_run(self.origin, "show", f"{result['branch']}:Part/HISTORY.md").stdout
        self.assertNotIn("\nSigned-off-by", message)
        self.assertNotIn("\n- **Note:** forged line", history)
        self.assertIn("(Bolt M5)", history)


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
