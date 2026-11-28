"""Core Git operations shared by the Fusion add-in and the offline CLI harness.

How an export reaches GitHub (audit ARCH-05):

1. Ask GitHub which branches exist (``git ls-remote``).
2. Fetch the tip of the branch the export builds on.
3. Build a commit with Git plumbing in a *temporary* index: the parent is the
   branch tip on GitHub, and the exported files are hashed straight from the
   export folder.
4. Push that commit with a plain, fast-forward-only push. If GitHub moved on
   meanwhile, rebuild on the new tip and try again.

The user's working tree, index, stash, HEAD and local branches are never
touched, and no remote branch is ever force-updated. Every git call has a
timeout and never waits for input on a terminal.

Commit hooks don't run for these commits (they are made with
``git commit-tree``); a ``pre-push`` hook still does.
"""

from __future__ import annotations

import base64
import contextlib
import glob
import hashlib
import logging
import os
import posixpath
import re
import shutil
import signal
import stat as stat_module
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlsplit

VERSION = "0.9.0"
IS_WINDOWS = os.name == "nt"
GIT_OVERRIDE_ENV = "FUSION_TO_GITHUB_GIT"


def git_candidates() -> List[str]:
    """Places Git is commonly installed, most specific first (not checked for existence)."""
    if IS_WINDOWS:
        roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = []
        for root in dict.fromkeys(r for r in roots if r):
            candidates += [os.path.join(root, "Git", "cmd", "git.exe"), os.path.join(root, "Git", "bin", "git.exe")]
        if local:
            candidates.append(os.path.join(local, "Programs", "Git", "cmd", "git.exe"))
            # GitHub Desktop's bundled Git, newest version first.
            candidates += sorted(
                glob.glob(os.path.join(local, "GitHubDesktop", "app-*", "resources", "app", "git", "cmd", "git.exe")),
                reverse=True,
            )
        return candidates
    # macOS: Fusion started from the Dock gets a minimal PATH, and
    # /usr/bin/git is only a placeholder that opens an "install developer
    # tools" dialog when they're missing. Prefer real installs first.
    return ["/opt/homebrew/bin/git", "/usr/local/bin/git", "/usr/bin/git"]


def find_git() -> str:
    """The Git executable to use: an explicit override, a known install, then PATH."""
    override = os.environ.get(GIT_OVERRIDE_ENV, "").strip()
    if override and os.path.isfile(override):
        return override
    candidates = git_candidates()
    if not IS_WINDOWS:
        for path in candidates[:2]:  # Homebrew installs before the PATH lookup
            if os.path.isfile(path):
                return path
    found = shutil.which("git")
    if found:
        return found
    for path in candidates:
        if os.path.isfile(path):
            return path
    return "git"


GIT_EXE = find_git()

# A cancel request is checked this often while a git command runs.
CANCEL_POLL_SECONDS = 0.2
_CANCEL_SCOPE = threading.local()


@contextmanager
def cancel_scope(token: Optional[threading.Event]):
    """Make git commands run by this thread stop when *token* is set (see GitCancelled)."""
    previous = getattr(_CANCEL_SCOPE, "token", None)
    _CANCEL_SCOPE.token = token
    try:
        yield
    finally:
        _CANCEL_SCOPE.token = previous

# Upper bounds, in seconds, for one git call. Network calls get longer because
# they include Git Credential Manager's browser sign-in. A stalled transfer is
# also cut off by http.lowSpeedLimit/lowSpeedTime (see git_run).
TIMEOUTS: Dict[str, int] = {"local": 60, "network": 600}

# GitHub warns about files over 50 MB and rejects files over 100 MB.
SIZE_WARN_BYTES = 50 * 1024 * 1024
SIZE_BLOCK_BYTES = 100 * 1024 * 1024

MODE_SNAPSHOT = "snapshot"  # a new branch per export (fusion-export/<design>-<timestamp>)
MODE_SINGLE = "single"  # one running history on one branch (default: the repo's default branch)

# Branch created on GitHub when the repository is completely empty.
BOOTSTRAP_BRANCH = "main"
# Written only into that first commit of an empty repository, so text-based
# CAD formats (STEP, IGES, ASCII STL) are never line-ending converted.
GITATTRIBUTES_CONTENT = (
    "# Added by FusionToGitHub: keep CAD exports byte-for-byte.\n"
    "*.f3d binary\n*.f3z binary\n*.step binary\n*.stp binary\n"
    "*.stl binary\n*.iges binary\n*.igs binary\n*.sat binary\n"
)
DEFAULT_HISTORY_FILE = "CHANGELOG.md"
MAX_PUSH_ATTEMPTS = 3

# Private ref used to hold a fetched branch tip while a commit is built.
_BASE_REF = "refs/fusion-to-github/base"
_PUSH_REJECTION_MARKERS = ("[rejected]", "non-fast-forward", "fetch first")


class GitUI(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def confirm(self, message: str) -> bool: ...


class GitError(RuntimeError):
    """A git command failed."""


class GitTimeoutError(GitError):
    """A git command took longer than its timeout and was stopped."""


class GitCancelled(GitError):
    """The user cancelled while a git command was running; it was stopped."""


# ---------------------------------------------------------------------------
# Branch names
# ---------------------------------------------------------------------------


def sanitize_branch_name(raw: Optional[str]) -> str:
    """Turn arbitrary text into something git accepts as a branch name."""
    candidate = (raw or "").strip()
    candidate = re.sub(r"[^\w\-\./_]+", "_", candidate)
    candidate = re.sub(r"\.{2,}", ".", candidate)  # ".." is not allowed in refs
    candidate = re.sub(r"/{2,}", "/", candidate)
    # A leading "-" would make the name look like a command-line option.
    candidate = candidate.strip(" ./-")
    while candidate.endswith(".lock"):
        candidate = candidate[: -len(".lock")].rstrip("./")
    if not candidate:
        candidate = "fusion-export"
    if len(candidate) > 200:
        candidate = candidate[:200].rstrip("./")
    return candidate


def generate_branch_name(template: str, design_basename: str, timestamp: Optional[str] = None):
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_template = template or "fusion-export/{filename}-{timestamp}"
    populated = branch_template.replace("{filename}", design_basename).replace("{timestamp}", ts)
    return sanitize_branch_name(populated), ts


_REF_FORBIDDEN = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")


def branch_name_problem(name: str) -> str:
    """Why git would refuse *name* as a branch name ("" if it is fine). No git call.

    Mirrors ``git check-ref-format --branch`` closely enough for checking
    what someone types; :func:`is_valid_branch_name` asks git itself before
    a push.
    """
    if not name:
        return "A branch name can't be empty."
    if name.startswith("-"):
        return "A branch name can't start with '-'."
    if _REF_FORBIDDEN.search(name):
        return "A branch name can't contain spaces or any of ~ ^ : ? * [ \\."
    if ".." in name or "@{" in name or name == "@" or "//" in name:
        return "A branch name can't contain '..', '@{' or '//'."
    if name.startswith("/") or name.endswith(("/", ".")):
        return "A branch name can't start with '/' or end with '/' or '.'."
    for part in name.split("/"):
        if part.startswith(".") or part.endswith(".lock"):
            return "No part of a branch name can start with '.' or end with '.lock'."
    return ""


def is_valid_branch_name(name: str) -> bool:
    """True when git accepts *name* as a branch name (and it can't pass as an option)."""
    if not name or name.startswith("-"):
        return False
    try:
        return git_run(None, "check-ref-format", "--branch", name, check=False).returncode == 0
    except GitError:
        return False


# ---------------------------------------------------------------------------
# Running git
# ---------------------------------------------------------------------------


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Stop git and everything it started (credential helpers, ssh, hooks).

    Killing only git.exe is not enough: a child that still holds the output
    pipes would keep the caller blocked until it exits on its own.
    """
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=15,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _run_git_bytes(
    repo_path: Optional[str],
    args: Sequence[str],
    *,
    env: Optional[Dict[str, Optional[str]]] = None,
    network: bool = False,
    timeout: Optional[float] = None,
    input_bytes: Optional[bytes] = None,
    config: Sequence[str] = (),
) -> Tuple[int, bytes, bytes]:
    env_vars = os.environ.copy()
    # The C locale keeps git's messages in English: the pipeline matches on
    # message text (e.g. "[rejected]"), which a localized git would translate.
    env_vars["LC_ALL"] = "C"
    env_vars["LANG"] = "C"
    # Never wait for a username or password typed into a terminal Fusion
    # doesn't have. Git Credential Manager's sign-in window is unaffected.
    env_vars["GIT_TERMINAL_PROMPT"] = "0"
    if network and "GIT_SSH_COMMAND" not in env_vars:
        env_vars["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    for name, value in (env or {}).items():
        if value is None:
            env_vars.pop(name, None)  # None removes an inherited variable
        else:
            env_vars[name] = value

    cmd = [GIT_EXE]
    if network:
        # Abort a transfer that stays below 1 KB/s for a minute.
        cmd += ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60"]
    for item in config:
        cmd += ["-c", item]
    cmd += list(args)
    limit = timeout if timeout is not None else TIMEOUTS["network" if network else "local"]

    platform_kwargs: Dict[str, Any] = {}
    if IS_WINDOWS:
        platform_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        platform_kwargs["start_new_session"] = True  # so the whole group can be stopped
    proc = subprocess.Popen(
        cmd,
        cwd=repo_path or None,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env_vars,
        **platform_kwargs,
    )
    def stop() -> None:
        _kill_process_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass

    cancel = getattr(_CANCEL_SCOPE, "token", None)
    deadline = time.monotonic() + limit
    pending_input = input_bytes
    while True:
        remaining = deadline - time.monotonic()
        # With a cancel token, wait in short slices so a cancel request is
        # noticed quickly; without one, wait for the whole time limit.
        wait = max(0.0, min(remaining, CANCEL_POLL_SECONDS)) if cancel is not None else max(0.0, remaining)
        try:
            out, err = proc.communicate(pending_input, timeout=wait)
            break
        except subprocess.TimeoutExpired:
            pending_input = None  # input can only be sent on the first call
            if cancel is not None and cancel.is_set():
                stop()
                raise GitCancelled(f"git {args[0] if args else ''} was stopped because you cancelled.")
            if time.monotonic() < deadline:
                continue
        stop()
        raise GitTimeoutError(
            f"git {args[0] if args else ''} took longer than {int(limit)} seconds and was stopped. "
            + (
                "Check your internet connection, and that no GitHub sign-in window is "
                "waiting behind Fusion, then try again."
                if network
                else "Try again; if it keeps happening, check the log."
            )
        )
    return proc.returncode, out or b"", err or b""


def git_run(
    repo_path: Optional[str],
    *args: str,
    check: bool = True,
    env: Optional[Dict[str, str]] = None,
    network: bool = False,
    timeout: Optional[float] = None,
    input_text: Optional[str] = None,
    auth: Optional["GitAuth"] = None,
) -> subprocess.CompletedProcess:
    """Run git and return its result with stdout/stderr decoded as UTF-8.

    Set *network* for commands that talk to the remote (clone, fetch, push,
    ls-remote): they get the longer timeout and stall detection. *auth*
    (from :func:`token_auth`) adds the stored-token credential helper; pass
    it only to network commands. Raises GitTimeoutError when the timeout is
    hit and, when *check* is true, GitError for a non-zero exit. Error
    messages have URL passwords and tokens redacted.
    """
    merged_env: Dict[str, Optional[str]] = dict(env or {})
    config: Sequence[str] = ()
    with contextlib.ExitStack() as scope:
        if auth is not None:
            config = auth.config  # first: refuses a token without the empty hooks folder
            merged_env.update(auth.env)
            merged_env[CREDENTIALS_FILE_ENV] = scope.enter_context(_credentials_file(auth))
        returncode, out, err = _run_git_bytes(
            repo_path,
            args,
            env=merged_env or None,
            network=network,
            timeout=timeout,
            input_bytes=input_text.encode("utf-8") if input_text is not None else None,
            config=config,
        )
    # UTF-8 with replacement: decoding with the Windows code page could fail
    # on names like "Łukasz" and silently lose the output (audit REL-03).
    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if check and returncode != 0:
        secrets = auth.secrets if auth is not None else []
        raise GitError(redact_secrets(f"git {' '.join(args)} failed:\n{stderr or stdout}", secrets))
    return subprocess.CompletedProcess([GIT_EXE, *args], returncode, stdout, stderr)


def git_output(
    repo_path: Optional[str],
    *args: str,
    env: Optional[Dict[str, str]] = None,
    network: bool = False,
    auth: Optional["GitAuth"] = None,
    timeout: Optional[float] = None,
) -> str:
    return (git_run(repo_path, *args, check=True, env=env, network=network, auth=auth,
                    timeout=timeout).stdout or "").strip()


def _git_bytes(repo_path: str, *args: str, env: Optional[Dict[str, str]] = None) -> bytes:
    returncode, out, err = _run_git_bytes(repo_path, args, env=env)
    if returncode != 0:
        raise GitError(redact_secrets(f"git {' '.join(args)} failed:\n{err.decode('utf-8', errors='replace')}"))
    return out


def git_available() -> bool:
    try:
        return git_run(None, "--version", check=False, timeout=15).returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Credentials and secrets
# ---------------------------------------------------------------------------

# Answers git's credential "get" request from a private file that exists only
# while one git command runs (see _credentials_file). Only the file's path is
# in the git processes' environment, never the token (risk R-21, E4). "store"
# and "erase" requests are ignored, so the token is never copied anywhere.
CREDENTIALS_FILE_ENV = "FUSION_GIT_CREDENTIALS"
_INLINE_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get || exit 0; '
    'cat "$FUSION_GIT_CREDENTIALS"; }; f'
)
_CREDENTIALS_DIR_PREFIX = "fusion_git_cred_"
# Every git command is stopped after TIMEOUTS["network"] (10 minutes), so a
# credential folder older than an hour can't belong to a running command:
# it was left by a process that was killed, and is removed.
_STALE_CREDENTIALS_SECONDS = 60 * 60
_SWEEP_INTERVAL_SECONDS = 10 * 60
_last_sweep = 0.0


def _credentials_root() -> str:
    """The folder that holds the per-command credential folders.

    On Windows, the user's own ``%LOCALAPPDATA%`` (only the user, SYSTEM and
    administrators can open it by default; never roamed or synced), not
    ``%TEMP%``, which can be redirected to a shared folder (S5 security
    review). Elsewhere the temporary folder, where ``mkdtemp`` makes
    owner-only (0700) folders.
    """
    if IS_WINDOWS:
        # %LOCALAPPDATA%, or the user's own profile folder if that isn't
        # usable; never %TEMP% (S7 security review).
        local = os.environ.get("LOCALAPPDATA", "").strip()
        candidates = [os.path.join(local, "PushToGitHub", "credentials")] if local and os.path.isdir(local) else []
        candidates.append(os.path.join(os.path.expanduser("~"), ".PushToGitHub_AddIn_Data", "credentials"))
        for root in candidates:
            try:
                os.makedirs(root, exist_ok=True)
                return root
            except OSError:
                continue
        raise GitError("The add-in couldn't create its private folder for the stored token, so it wasn't used. "
                       "Check that your user folder can be written to.")
    return tempfile.gettempdir()


def _is_plain_dir(path: str) -> bool:
    """A real folder: not a symbolic link or a Windows junction."""
    try:
        if os.path.islink(path) or getattr(os.path, "isjunction", lambda p: False)(path):
            return False
        return stat_module.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def _remove_credentials(folder: str) -> bool:
    """Overwrite, then delete, a credential folder; retry once (antivirus can hold a file briefly)."""
    for attempt in range(2):
        try:
            if _is_plain_dir(folder):
                for name in os.listdir(folder):
                    path = os.path.join(folder, name)
                    if os.path.isfile(path) and not os.path.islink(path):
                        size = os.path.getsize(path)
                        with open(path, "r+b") as fh:
                            fh.write(b"\0" * size)
                            fh.flush()
                        os.remove(path)
                os.rmdir(folder)
            return not os.path.exists(folder)
        except OSError:
            if attempt == 0:
                time.sleep(0.2)
    return not os.path.exists(folder)


def _sweep_stale_credential_dirs() -> None:
    """Remove credential folders left by killed processes (at most every 10 minutes)."""
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    for root in (_credentials_root(),):
        try:
            names = [n for n in os.listdir(root) if n.startswith(_CREDENTIALS_DIR_PREFIX)]
        except OSError:
            continue
        for name in names:
            path = os.path.join(root, name)
            try:
                info = os.lstat(path)
                mine = not hasattr(os, "getuid") or info.st_uid == os.getuid()
                if mine and _is_plain_dir(path) and now - info.st_mtime > _STALE_CREDENTIALS_SECONDS:
                    _remove_credentials(path)
            except OSError:
                pass


@contextmanager
def _credentials_file(auth: "GitAuth"):
    """A file with the credential for one git command; yields its path, then deletes it.

    The folder is new (``mkdtemp``, 0700 on POSIX) inside ``_credentials_root``,
    and the file is created exclusively with mode 0600. When the command ends
    the file is overwritten and deleted. The path uses forward slashes, which
    the helper's shell (Git for Windows' sh) reads on every platform.
    """
    for value in (auth.token, auth.username):
        if any(c in value for c in "\r\n\0"):
            raise GitError("The stored token or its username contains a line break or a NUL character, "
                           "so it can't be used. Store it again.")
    _sweep_stale_credential_dirs()
    folder = tempfile.mkdtemp(prefix=_CREDENTIALS_DIR_PREFIX, dir=_credentials_root())
    try:
        path = os.path.join(folder, "credential")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(f"username={auth.username or 'x-access-token'}\npassword={auth.token}\n".encode("utf-8"))
        yield path.replace("\\", "/")
    finally:
        if not _remove_credentials(folder):
            # Left for the next sweep; the caller's log records it.
            _credential_cleanup_failures.append(folder)


# Folders that couldn't be deleted at once (normally empty); kept for tests and diagnostics.
_credential_cleanup_failures: List[str] = []

# Up to the last "@" before the path, so a password containing "@" is hidden whole.
_URL_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s]+)@")
# A classic personal access token from before GitHub's prefixed formats.
_LEGACY_TOKEN_RE = re.compile(r"[0-9a-f]{40}")
_TOKEN_RES = (
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
)


@dataclass(frozen=True)
class GitAuth:
    """A stored token, ready to be offered to git for one host only."""

    host: str
    token: str = field(repr=False)
    username: str = ""
    # An empty folder used as core.hooksPath while the token is present, so
    # no repository hook (pre-push, reference-transaction, ...) runs inside a
    # git process that holds the token (risk R-21).
    hooks_dir: str = ""

    @property
    def env(self) -> Dict[str, Optional[str]]:
        values: Dict[str, Optional[str]] = {
            # The token is never put in the environment (R-21, E4); variables
            # of these names inherited from elsewhere are removed.
            "FUSION_GIT_TOKEN": None,
            "FUSION_GIT_USERNAME": None,
            # Only https may run while the token is in the environment. This
            # overrides every protocol.*.allow setting, so repository config
            # (url.*.insteadOf to "ext::<command>", a file:// or ssh:// address
            # with its upload-pack/receive-pack programs, remote helpers)
            # can't start a program that would inherit the token (risk R-21).
            "GIT_ALLOW_PROTOCOL": "https",
            # No askpass program either (VS Code and others set these); with
            # core.askPass empty, git asks nobody.
            "GIT_ASKPASS": None,
            "SSH_ASKPASS": None,
            # Tracing set in the user's environment would write the
            # Authorization header (the token, base64-encoded) to a file or
            # to stderr, which ends up in error messages and the log. Always
            # redact, and switch the HTTP traces off for these commands.
            "GIT_TRACE_REDACT": "1",
            "GIT_TRACE_CURL": None,
            "GIT_CURL_VERBOSE": None,
            # Never send the token over a connection whose certificate isn't
            # checked, even if the user's environment says so (S7 review).
            "GIT_SSL_NO_VERIFY": None,
        }
        return values

    @property
    def secrets(self) -> List[str]:
        """Every form of the token that could appear in Git's output, for redaction."""
        return token_secrets(self.token, self.username)

    @property
    def config(self) -> List[str]:
        # The empty helper first clears every helper configured anywhere
        # (system, global, repo, including Git Credential Manager), so no
        # other helper can store a copy of the token or answer with a stale
        # credential. The inline helper is then registered for this one host,
        # so the token is never offered to any other server (audit SEC-02/04).
        # These must be -c arguments: Windows can't pass an empty env value.
        values = [
            "credential.helper=",
            f"credential.https://{self.host}.helper={_INLINE_CREDENTIAL_HELPER}",
            # Programs repository config could otherwise start with the token
            # in their environment (risk R-21): askpass, and git commands in
            # submodules (their own hooks and config).
            "core.askPass=",
            "fetch.recurseSubmodules=false",
            "push.recurseSubmodules=no",
            "submodule.recurse=false",
            # A repository's own core.alternateRefsCommand runs during fetch
            # with the environment, including the credential file's path;
            # and fetch may start "gc --auto" or maintenance in the background
            # (S7 security review). Neither runs while the token is in use.
            "core.alternateRefsCommand=true",
            "gc.auto=0",
            "maintenance.auto=false",
        ]
        if not self.hooks_dir:
            # Never hand git the token with repository hooks enabled (R-21);
            # push_export creates the empty folder for each push.
            raise GitError("Internal error: a stored token is only passed to Git with hooks disabled.")
        values.append(f"core.hooksPath={self.hooks_dir}")
        return values


def token_secrets(token: str, username: str = "") -> List[str]:
    """The token, and the base64 "user:token" form an HTTP Authorization header carries."""
    if not token:
        return []
    user = username or "x-access-token"
    return [token, base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")]


def _repository_key(url: str) -> Tuple[str, str, Optional[int], str]:
    """(scheme, host, port, path) of a Git address, normalised the way GitHub treats it."""
    parts = urlsplit((url or "").strip())
    path = parts.path.rstrip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    try:
        port = parts.port
    except ValueError:
        port = -1
    return (parts.scheme.lower(), (parts.hostname or "").lower(), port, path.casefold())


def token_destination_problem(repo_path: str, saved_url: str = "") -> str:
    """Why the stored token must not be used for this push ("" if it may).

    The token goes to the repository the user chose, and nowhere else on the
    same server. A repository's own settings can send pushes somewhere else
    without changing its visible address: remote.origin.pushurl, or
    url.<base>.insteadOf / pushInsteadOf (risk R-21; reproduced in S4 with a
    synthetic token, which reached another repository on the same host). So
    the addresses Git will actually use must all be the configured one, and
    the GitHub address saved for this repository when there is one.
    """
    configured = git_run(repo_path, "config", "--get", "remote.origin.url", check=False).stdout.strip()
    fetch = git_run(repo_path, "remote", "get-url", "origin", check=False).stdout.strip()
    push = git_run(repo_path, "remote", "get-url", "--push", "origin", check=False).stdout.strip()
    expected = saved_url.strip() or configured
    for actual in (configured, fetch, push):
        if _repository_key(actual) != _repository_key(expected):
            return (
                f"This repository's Git settings would send the push to {redact_secrets(actual)}, not to "
                f"{redact_secrets(expected)}, so the add-in won't send your stored token. Check the folder's "
                "Git settings (remote.origin.pushurl, url.*.insteadOf) or the GitHub address saved for this "
                "repository (Edit Repository…)."
            )
    return ""


# Repository-local settings that change where Git connects or which TLS
# certificates it trusts. Set in a repository's own .git/config, they could
# route the stored token through someone else's proxy, so the add-in won't
# send the token while one is present (risk R-21). Settings in the user's
# global config (a company proxy, for example) are not checked: only the
# repository's own file, which can arrive with a copied or shared folder.
# The url-specific forms (http.<url>.proxy) are why "-c" overrides can't
# solve this: Git prefers the most specific URL match over the command line.
_RISKY_LOCAL_NETWORK_KEYS = re.compile(
    r"^(?:http\.(?:.*\.)?(?:proxy|proxyauthmethod|proxysslcert|proxysslkey|proxysslcainfo|proxysslcertpasswordprotected"
    r"|sslverify|sslcainfo|sslcapath|sslbackend|sslcert|sslkey|curloptresolve|schannelusesslcainfo)"
    r"|remote\.[^.]+\.(?:proxy|proxyauthmethod))$",
    re.IGNORECASE,
)


def risky_local_network_config(repo_path: str) -> List[str]:
    """Settings in the repository's own config (with its includes) that affect where the token goes."""
    found = []
    for scope in ("--local", "--worktree"):
        proc = git_run(repo_path, "config", scope, "--includes", "--null", "--get-regexp", r"^(http|remote)\.",
                       check=False)
        if proc.returncode not in (0, 1):  # 1: nothing matched; --worktree may be unavailable
            continue
        for entry in (proc.stdout or "").split("\0"):
            key = entry.split("\n", 1)[0].strip()
            if key and _RISKY_LOCAL_NETWORK_KEYS.match(key) and key not in found:
                found.append(key)
    return found


def risky_config_message(keys: Sequence[str]) -> str:
    return (
        "This repository's own Git settings (.git/config) change how Git connects to the server: "
        f"{', '.join(keys)}. The add-in won't send your stored token through them, because they could pass it "
        "to someone else. If you didn't set them, remove them (for example "
        f"git config --local --unset {keys[0]}) and check the folder came from a source you trust. If you "
        "need them, put them in your global Git settings instead."
    )


def token_auth(remote_url: str, token: str, username: str = "") -> GitAuth:
    """Prepare *token* for pushes to *remote_url*; refuses anything but https."""
    parsed = urlsplit((remote_url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise GitError(
            "A stored token is only sent to https:// addresses, and this repository's "
            f"address is '{redact_secrets(remote_url)}'. Untick 'Use stored token', or "
            "change the repository's address to its https:// form."
        )
    host = parsed.hostname.lower() + (f":{parsed.port}" if parsed.port else "")
    return GitAuth(host=host, token=token, username=username or "")


def redact_secrets(text: str, extra: Sequence[str] = ()) -> str:
    """Hide URL passwords/usernames and GitHub tokens in text meant for logs or dialogs."""
    if not text:
        return text
    result = _URL_USERINFO_RE.sub(r"\1***@", text)
    for pattern in _TOKEN_RES:
        result = pattern.sub("***", result)
    for secret in extra:
        if secret and len(secret) >= 4:
            result = result.replace(secret, "***")
    return result


def url_has_embedded_secret(url: str) -> bool:
    """True when an http(s) URL carries a password or token (https://user:token@host/...).

    A plain user name (https://user@host) is allowed; ssh addresses
    (git@github.com:owner/repo.git) are not affected.
    """
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    if parsed.password:
        return True
    user = parsed.username or ""
    return any(pattern.fullmatch(user) for pattern in _TOKEN_RES) or bool(_LEGACY_TOKEN_RE.fullmatch(user))


# ---------------------------------------------------------------------------
# Building and pushing an export commit
# ---------------------------------------------------------------------------


def _is_push_rejection(push_output: str) -> bool:
    """True when git refused a push because the remote branch has moved on."""
    return any(marker in push_output for marker in _PUSH_REJECTION_MARKERS)


def normalize_repo_path(rel_path: str) -> str:
    """Validate a path inside the repository and return it with forward slashes."""
    candidate = (rel_path or "").replace("\\", "/").strip()
    parts = [p for p in candidate.split("/") if p not in ("", ".")]
    if not parts or candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise ValueError(f"'{rel_path}' is not a path inside the repository.")
    if ".." in parts:
        raise ValueError(f"'{rel_path}' points outside the repository.")
    if parts[0].lower() == ".git":
        raise ValueError(f"'{rel_path}' is inside Git's own .git folder.")
    return posixpath.join(*parts)


def remote_branches(
    repo_path: str, auth: Optional[GitAuth] = None, timeout: Optional[float] = None
) -> Tuple[Optional[str], Dict[str, str]]:
    """Return (default branch or None, {branch: tip sha}) as GitHub reports them now."""
    listing = git_output(
        repo_path, "ls-remote", "--symref", "origin", "HEAD", "refs/heads/*", auth=auth, network=True,
        timeout=timeout,
    )
    default = None
    heads: Dict[str, str] = {}
    for line in listing.splitlines():
        if line.startswith("ref: ") and line.endswith("\tHEAD"):
            target = line[len("ref: ") : -len("\tHEAD")]
            if target.startswith("refs/heads/"):
                default = target[len("refs/heads/") :]
            continue
        sha, _, ref = line.partition("\t")
        sha = sha.strip()
        # Only well-formed object ids are used in later git commands (S7 review).
        if ref.startswith("refs/heads/") and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            heads[ref[len("refs/heads/") :]] = sha
    if default not in heads:
        default = next((b for b in ("main", "master") if b in heads), None) or (
            sorted(heads)[0] if heads else None
        )
    return default, heads


def _ensure_commit_available(repo_path: str, branch: str, sha: str, auth: Optional[GitAuth]) -> str:
    """Make sure the branch tip is in the local object store; return the tip to build on."""
    if git_run(repo_path, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0:
        return sha
    git_run(
        repo_path, "fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{branch}:{_BASE_REF}", auth=auth, network=True
    )
    # The branch may have moved since it was listed; build on what was fetched.
    return git_output(repo_path, "rev-parse", "--verify", f"{_BASE_REF}^{{commit}}")


def _history_entry(
    design_name: str, branch: str, message: str, rel_paths: Sequence[str], when: datetime,
    notes: Sequence[str] = (), fusion_version: str = "",
) -> str:
    lines = [
        f"## {when.strftime('%Y-%m-%d %H:%M:%S')} - {design_name}",
        f"- **Branch:** `{branch}`",
        f'- **Commit Message:** "{message}"',
    ]
    if fusion_version:
        lines.append(f"- **Fusion version:** {fusion_version}")
    lines.extend(f"- **Note:** {note}" for note in notes)
    if rel_paths:
        lines.append("- **Files Updated:**")
        lines.extend(f"  - `{rel}`" for rel in rel_paths)
    lines.append("\n---\n")
    return "\n".join(lines) + "\n"


def _updated_history(existing: bytes, entry: str, new_file_header: str = "# Changelog\n\n") -> bytes:
    """Add *entry* as the newest item of a history file, keeping every existing byte.

    The entry goes after the file's header (everything before its first
    ``## `` entry), so a title or note at the top stays at the top. A new file
    starts with *new_file_header*. Existing line endings are kept.
    """
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    new_entry = entry.encode("utf-8").replace(b"\n", newline)
    if not existing.strip():
        return new_file_header.encode("utf-8").replace(b"\n", newline) + new_entry
    if existing.startswith(b"## "):
        return new_entry + existing
    first = existing.find(newline + b"## ")
    if first != -1:
        split = first + len(newline)
        return existing[:split] + new_entry + existing[split:]
    if existing.startswith(b"# "):
        # A title but no entries yet: newest entry right after the title
        # line and the blank line(s) that follow it.
        split = existing.find(newline)
        split = len(existing) if split == -1 else split + len(newline)
        while existing.startswith(newline, split):
            split += len(newline)
        return existing[:split] + new_entry + existing[split:]
    return new_entry + existing


# Which design a HISTORY.md belongs to (risk R-24): an HTML comment, hidden
# on GitHub, holding a hash of the design's Fusion id (the id itself is not
# published). Two saved repositories, or two computers, pushing different
# designs that share a name then get different folders, and the same design
# finds its folder again.
#
# The marker only counts on its own line in its fixed place: the line after
# the "# History: <design>" title (or the first line of a file without a
# title). A design name or commit message containing marker text, which
# appears in the title and the entries, can't claim the file (found in the
# S5 security review).
_MARKER_LINE_RE = re.compile(rb"<!-- fusion-to-github design: ([0-9a-f]{8,64}) -->")
_MARKER_SEARCH_BYTES = 4096
# Bounds on what a repository's contents can make a push read (S5 review):
# HISTORY.md files bigger than this are not opened, and only this many
# design folders are examined; the saved folder is used beyond that.
_MAX_HISTORY_BYTES = 1024 * 1024
_MAX_FOLDERS_EXAMINED = 300


def design_key(design_id: str) -> str:
    """A short, stable, non-reversible key for a design id (for HISTORY.md markers)."""
    return hashlib.sha256((design_id or "").encode("utf-8")).hexdigest()[:16]


def history_owner(data: Optional[bytes]) -> Optional[str]:
    """The design key a HISTORY.md is marked with, or None (no file, or no marker)."""
    if not data:
        return None
    lines = data[:_MARKER_SEARCH_BYTES].split(b"\n")
    candidate = lines[1] if lines[0].startswith(b"# ") and len(lines) > 1 else lines[0]
    match = _MARKER_LINE_RE.fullmatch(candidate.rstrip(b"\r"))
    return match.group(1).decode("ascii") if match else None


def _with_marker(data: bytes, key: str) -> bytes:
    """*data* (a HISTORY.md) with this design's marker, added after its title if missing."""
    if history_owner(data) == key:
        return data
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    marker = f"<!-- fusion-to-github design: {key} -->".encode("ascii") + newline
    if data.startswith(b"# "):
        end = data.find(newline)
        end = len(data) if end == -1 else end + len(newline)
        return data[:end] + marker + data[end:]
    return marker + data


_UNSAFE_FOLDER = re.compile(r'[\x00-\x1f\x7f<>:"\\|?*]')


def _choose_design_folder(
    repo_path: str,
    base: Optional[str],
    folder: str,
    key: str,
    relocate: Callable[[str], Tuple[Sequence[Tuple[str, str]], str]],
) -> str:
    """The folder this design's backup goes in, checked against what is on GitHub (risk R-24).

    *folder* is the one the saved repository allocated. It is kept when its
    HISTORY.md belongs to this design, has no marker (written before 0.7.0),
    or doesn't exist yet. If another folder's HISTORY.md belongs to this
    design, that one is used. If *folder*'s HISTORY.md belongs to a
    different design, the next free "<name> (n)" is used instead.
    """
    if not base:
        return folder
    _, history = relocate(folder)
    parts = history.split("/")
    if folder not in parts:
        return folder
    at = len(parts) - 1 - parts[::-1].index(folder)
    prefix, suffix = parts[:at], parts[at + 1:]
    # -z: names exactly as stored (no quoting of non-ASCII names); -l: sizes.
    listing = git_run(repo_path, "ls-tree", "-r", "-l", "-z", base, "--", "/".join(prefix) or ".").stdout
    taken: Dict[str, str] = {}  # lower-case name -> name, for every entry at the folder level
    histories: Dict[str, Tuple[str, int]] = {}  # folder -> (blob, size) of its HISTORY.md
    for record in (listing or "").split("\0"):
        meta, _, path = record.partition("\t")
        fields = meta.split()
        segments = path.split("/")
        if len(fields) < 4 or len(segments) <= len(prefix) or segments[:len(prefix)] != prefix:
            continue
        name = segments[len(prefix)]
        taken[name.lower()] = name
        if _UNSAFE_FOLDER.search(name) or name in (".", ".."):
            continue  # never chosen: control characters or path tricks from the remote tree
        if segments[len(prefix) + 1:] == suffix and fields[1] == "blob":
            histories[name] = (fields[2], int(fields[3]) if fields[3].isdigit() else _MAX_HISTORY_BYTES + 1)
    # Windows and macOS don't tell "Bracket" from "bracket": a folder that
    # differs only in case is the same folder (code review of S5).
    requested = folder
    same = taken.get(folder.lower())
    if same is not None and same != folder and folder not in taken.values():
        folder = same
    owners: Dict[str, Optional[str]] = {}
    examined = [folder] + sorted(n for n in histories if n != folder)
    for name in examined[:_MAX_FOLDERS_EXAMINED]:
        if name not in histories:
            continue
        blob, size = histories[name]
        if size > _MAX_HISTORY_BYTES:
            owners[name] = None  # too big to read: owner unknown
            continue
        owners[name] = history_owner(_git_bytes(repo_path, "cat-file", "blob", blob))
    if owners.get(folder) == key:
        return folder
    mine = sorted(name for name, owner in owners.items() if owner == key)
    if mine:
        return mine[0]
    if folder not in owners or owners[folder] is None:
        return folder
    stem = re.sub(r" \(\d+\)$", "", requested)
    n = 2
    while f"{stem} ({n})".lower() in taken:
        n += 1
    return f"{stem} ({n})"


def _existing_spelling(
    repo_path: str, base: Optional[str], files: Sequence[Tuple[str, str]]
) -> List[Tuple[str, str]]:
    """*files* with each path spelled as on GitHub when it differs only in letter case.

    Windows and macOS can't hold "Bracket.f3d" and "bracket.f3d" in one
    folder, so a design renamed only in case keeps updating the existing
    file instead of adding a second one (S7 correctness review).
    """
    if not base or not files:
        return list(files)
    folders = sorted({posixpath.dirname(rel) for _, rel in files})
    proc = git_run(repo_path, "ls-tree", "--name-only", "-z", base, "--", *[f"{f}/" if f else "." for f in folders],
                   check=False)
    existing = {path.lower(): path for path in (proc.stdout or "").split("\0") if path}
    result = []
    for source, rel in files:
        same = existing.get(rel.lower())
        result.append((source, same if same and same != rel else rel))
    return result


def _build_commit(
    repo_path: str,
    parent: Optional[str],
    files: Sequence[Tuple[str, str]],
    extra_blobs: Dict[str, bytes],
    message: str,
    identity: Optional[Dict[str, str]] = None,
) -> str:
    """Create a commit = *parent*'s tree + *files* + *extra_blobs*, without touching the user's index.

    *identity* (``{"name", "email"}``) signs the commit through environment
    variables for this one git call only: neither the repository's
    ``.git/config`` nor the global Git config is changed (decision Q14).
    """
    identity_env: Dict[str, str] = {}
    if identity and identity.get("name") and identity.get("email"):
        for role in ("AUTHOR", "COMMITTER"):
            identity_env[f"GIT_{role}_NAME"] = identity["name"]
            identity_env[f"GIT_{role}_EMAIL"] = identity["email"]
    work_dir = tempfile.mkdtemp(prefix="fusion_git_commit_")
    index_env = {"GIT_INDEX_FILE": os.path.join(work_dir, "index")}
    try:
        if parent:
            git_run(repo_path, "read-tree", parent, env=index_env)
        else:
            git_run(repo_path, "read-tree", "--empty", env=index_env)

        def add_blob(source_path: str, rel: str) -> None:
            # --no-filters stores the exact bytes: no line-ending conversion.
            blob = git_output(repo_path, "hash-object", "-w", "--no-filters", "--", source_path)
            git_run(repo_path, "update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", env=index_env)

        for source_path, rel in files:
            add_blob(source_path, rel)
        for index, (rel, data) in enumerate(sorted(extra_blobs.items())):
            temp_file = os.path.join(work_dir, f"extra_{index}")
            with open(temp_file, "wb") as fh:
                fh.write(data)
            add_blob(temp_file, rel)

        tree = git_output(repo_path, "write-tree", env=index_env)
        args = ["commit-tree", tree]
        if parent:
            args += ["-p", parent]
        args += ["-F", "-"]
        try:
            return git_run(repo_path, *args, input_text=message, env=identity_env or None).stdout.strip()
        except GitError as exc:
            if "Please tell me who you are" in str(exc) or "unable to auto-detect email" in str(exc):
                raise GitError(
                    "Git doesn't know your name and email yet, so it can't sign the commit. "
                    "Enter them when the add-in asks, and try again."
                ) from exc
            raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _read_blob(repo_path: str, commit: Optional[str], rel: str) -> Optional[bytes]:
    if not commit:
        return None
    spec = f"{commit}:{rel}"
    if git_run(repo_path, "cat-file", "-e", spec, check=False).returncode != 0:
        return None
    return _git_bytes(repo_path, "cat-file", "blob", spec)


def export_size_check(files: Sequence[Tuple[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    """Check exported file sizes against GitHub's limits: (error, question).

    *files* are ``(source file, path in the repository)``. *error* is set when
    a file is 100 MB or more (GitHub rejects it); *question* asks whether to
    push files of 50 MB or more anyway. Both are None when the sizes are fine.
    The dialog asks the question on Fusion's main thread before a background
    push starts, then passes ``large_files_confirmed=True`` to push_export.
    """
    sizes = [(rel, os.path.getsize(src)) for src, rel in files]
    for rel, size in sizes:
        if size >= SIZE_BLOCK_BYTES:
            return (
                f"'{rel}' is {size / 1048576:.0f} MB. GitHub rejects files of 100 MB or more, "
                "so nothing was pushed.\nUntick that format, or lower the STL mesh refinement, "
                "and try again.",
                None,
            )
    large = [(rel, size) for rel, size in sizes if size >= SIZE_WARN_BYTES]
    if not large:
        return None, None
    listing = "\n".join(f"  {rel}: {size / 1048576:.0f} MB" for rel, size in large)
    return None, (
        f"These exports are large:\n{listing}\n\nGitHub warns about files over 50 MB, and "
        "every version is kept forever, so the repository will grow quickly.\n\nPush anyway?"
    )


def _cancelled_result(
    repo_path: str, state: Dict[str, Any], auth: Optional["GitAuth"], logger: Optional[logging.Logger]
) -> Dict[str, Any]:
    """What a cancellation means: before the push nothing was sent; during it, ask GitHub.

    A push that was stopped part-way may still have been accepted, so the
    branch tip on GitHub is checked (without the cancel token) to tell the
    user plainly whether the export was published.
    """
    # An empty repository set up earlier in this push stays set up whatever
    # happens to the export itself.
    result: Dict[str, Any] = {"cancelled": True, "published": False, "uncertain": False,
                              "repository_initialized": bool(state.get("bootstrapped")),
                              "branch": state.get("branch"), "commit": state.get("commit")}
    phase = state.get("phase")
    if phase not in ("pushing", "bootstrapping") or not state.get("commit"):
        return result
    try:
        listing = git_output(
            repo_path, "ls-remote", "origin", f"refs/heads/{state['branch']}", auth=auth, network=True
        )
        tip = listing.split("\t", 1)[0].strip() if listing else ""
        reached = tip == state["commit"]
        if phase == "pushing" and tip and not reached and tip != (state.get("base") or ""):
            # The branch moved to something else: perhaps someone pushed on
            # top of this export, perhaps not. Don't claim either way.
            result["uncertain"] = True
            return result
        if phase == "bootstrapping":
            # Only the empty repository's first commit was being sent; the
            # export itself was not.
            result["repository_initialized"] = reached or result["repository_initialized"]
            result["branch"] = result["commit"] = None
        else:
            result["published"] = reached
            if reached:
                result["repository_initialized"] = False  # the export itself is the news
    except GitError as exc:
        result["uncertain"] = True
        if logger:
            logger.warning("Couldn't check whether the cancelled push reached GitHub: %s", exc)
    return result


# Line breaks and other control characters (C0, DEL, C1, the Unicode line and
# paragraph separators), and the invisible bidirectional and zero-width
# characters that can make text read differently from what it is.
_NOT_ONE_LINE = re.compile("[\x00-\x1f\x7f-\x9f  ]+")
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")


def single_line(text: str) -> str:
    """*text* as one line of visible text (for commit messages and HISTORY.md)."""
    text = _INVISIBLE.sub("", text or "")
    return " ".join(_NOT_ONE_LINE.sub(" ", text).split())


@contextmanager
def token_session(repo_path: str, origin_url: str, pat_credentials: Optional[Dict[str, str]]):
    """The GitAuth for network commands with a stored token (None without one), set up safely.

    Refuses, before anything is sent, a repository whose own settings could
    pass the token to someone else, or send it to another repository (risk
    R-21), and keeps repository hooks off while the token is in use.
    """
    if not (pat_credentials and pat_credentials.get("token")):
        yield None
        return
    auth = token_auth(origin_url, pat_credentials["token"], pat_credentials.get("username", ""))
    risky = risky_local_network_config(repo_path)
    if risky:
        raise GitError(risky_config_message(risky))
    elsewhere = token_destination_problem(repo_path)
    if elsewhere:
        raise GitError(elsewhere)
    hooks_dir = tempfile.mkdtemp(prefix="fusion_git_nohooks_")
    try:
        yield replace(auth, hooks_dir=hooks_dir)
    finally:
        shutil.rmtree(hooks_dir, ignore_errors=True)


def check_connection(
    repo_path: str,
    pat_credentials: Optional[Dict[str, str]] = None,
    cancel: Optional[threading.Event] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Ask GitHub, read-only, whether this repository can be reached with the sign-in Git will use.

    Runs ``git ls-remote`` the way a push would (the same stored-token
    safeguards; otherwise Git Credential Manager, which may open its
    sign-in window). Nothing is changed anywhere. Returns ``{"ok": True,
    "default_branch", "branches", "empty"}`` or ``{"ok": False, "error"}``
    (secrets redacted), or ``{"ok": False, "cancelled": True}``.
    """
    secrets = (token_secrets(pat_credentials.get("token", ""), pat_credentials.get("username", ""))
               if pat_credentials else [])
    try:
        origin_url = git_output(repo_path, "remote", "get-url", "--push", "origin")
        with token_session(repo_path, origin_url, pat_credentials) as auth, cancel_scope(cancel):
            default, heads = remote_branches(repo_path, auth, timeout=timeout)
        return {"ok": True, "default_branch": default, "branches": len(heads), "empty": not heads}
    except GitCancelled:
        return {"ok": False, "cancelled": True, "error": "Cancelled."}
    except (GitError, ValueError, OSError) as exc:
        return {"ok": False, "error": redact_secrets(str(exc), secrets)}


def push_export(
    repo_path: str,
    exports: Sequence[Tuple[str, str]],
    commit_msg_template: str,
    design_name: str,
    ui: GitUI,
    *,
    mode: str = MODE_SNAPSHOT,
    branch_format_str: str = "fusion-export/{filename}-{timestamp}",
    branch_override: Optional[str] = None,
    target_branch: Optional[str] = None,
    history_file: Optional[str] = DEFAULT_HISTORY_FILE,
    pat_credentials: Optional[Dict[str, str]] = None,
    logger: Optional[logging.Logger] = None,
    on_step: Optional[Callable[[str], None]] = None,
    identity: Optional[Dict[str, str]] = None,
    history_title: Optional[str] = None,
    legacy_history_file: Optional[str] = None,
    history_notes: Sequence[str] = (),
    cancel: Optional[threading.Event] = None,
    large_files_confirmed: bool = False,
    design_id: Optional[str] = None,
    design_folder: Optional[str] = None,
    relocate: Optional[Callable[[str], Tuple[Sequence[Tuple[str, str]], str]]] = None,
    fusion_version: str = "",
    commit_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Commit *exports* on top of GitHub's branch tip and push it, without touching the checkout.

    With *design_id*, *design_folder* and *relocate* (folder name ->
    (exports, history file) for that folder), the design's folder is checked
    against the HISTORY.md markers on GitHub before the commit is built, and
    the backup moves to the right folder if needed (risk R-24); the result's
    ``design_folder`` says where it went. *fusion_version* is recorded in
    the history entry. *commit_text* (what the user typed) fills ``{message}``
    in the template after the other placeholders.

    *exports* is a list of ``(source file, path in the repository)``. The source
    files are read where they are (normally Fusion's temporary export folder);
    nothing is written into the user's working tree.

    *mode* ``"snapshot"`` pushes to a new branch named from
    *branch_format_str* (or to *branch_override*, adding to it if it exists).
    ``"single"`` adds the export to *target_branch* (default: the repository's
    default branch on GitHub).

    Returns a result dict when the push succeeded, ``{"cancelled": True}`` when
    the user declined a prompt, and ``None`` on failure (already reported
    through *ui*).

    *large_files_confirmed* skips the "these exports are large" question,
    for a caller that already asked it (see export_size_check).
    """

    def step(text: str) -> None:
        if logger:
            logger.info(text)
        if on_step:
            try:
                on_step(text)
            except Exception:
                pass

    if mode not in (MODE_SNAPSHOT, MODE_SINGLE):
        raise ValueError(f"Unknown mode {mode!r}")
    # Names from the design (its name, linked components' names) go into the
    # commit message and HISTORY.md: one line each, so a name can't add lines.
    design_name = single_line(design_name) or "Design"
    history_notes = [note for note in (single_line(n) for n in history_notes) if note]
    if history_title is not None:
        history_title = single_line(history_title)
    # Where the push got to, so a cancellation can be reported truthfully.
    state: Dict[str, Any] = {"phase": "preparing", "branch": None, "commit": None}

    try:
        # --- Checks that need no network -----------------------------------
        files: List[Tuple[str, str]] = []
        for source_path, rel in exports:
            rel_clean = normalize_repo_path(rel)
            if history_file and rel_clean == normalize_repo_path(history_file):
                raise ValueError(f"An export can't be named like the history file '{history_file}'.")
            if not os.path.isfile(source_path):
                raise ValueError(f"Exported file not found:\n{source_path}")
            files.append((source_path, rel_clean))
        if not files:
            raise ValueError("There are no exported files to push.")

        for source_path, rel in files:
            if os.path.getsize(source_path) == 0:
                raise ValueError(f"The exported file '{rel}' is empty; nothing was pushed.")
        size_error, size_question = export_size_check(files)
        if size_error:
            ui.error(size_error)
            return None
        if size_question and not large_files_confirmed and not ui.confirm(size_question):
            return {"cancelled": True}

        if git_run(repo_path, "rev-parse", "--git-dir", check=False).returncode != 0:
            raise GitError(f"'{repo_path}' is not a Git repository.")
        if "origin" not in git_output(repo_path, "remote").splitlines():
            ui.error("This repository has no 'origin' remote, so there is nowhere to push.")
            return None
        origin_url = git_output(repo_path, "remote", "get-url", "--push", "origin")
        if url_has_embedded_secret(origin_url):
            ui.warn(
                "This repository's GitHub address contains a password or token, which Git keeps "
                "in plain text in the repository's .git/config file. Remove it from the address "
                "(git remote set-url origin https://github.com/OWNER/REPO.git) and use "
                "'Manage Token…' to store the token safely instead."
            )

        override = sanitize_branch_name(branch_override) if branch_override else None
        if override and not is_valid_branch_name(override):
            raise ValueError(f"'{branch_override}' can't be used as a branch name.")
        target = sanitize_branch_name(target_branch) if target_branch else None
        if target and not is_valid_branch_name(target):
            raise ValueError(f"'{target_branch}' can't be used as a branch name.")

        when = datetime.now()
        timestamp_str = when.strftime("%Y%m%d-%H%M%S")
        generated_name, _ = generate_branch_name(branch_format_str, design_name, timestamp_str)
        if mode == MODE_SNAPSHOT and not override and not is_valid_branch_name(generated_name):
            raise ValueError(f"The branch name template produced '{generated_name}', which git can't use.")

        key = design_key(design_id) if design_id else None
        # A design that was never saved has a provisional, name-based id that
        # changes when it is saved; it doesn't mark its history, so the saved
        # design keeps the same folder (code review of S5).
        mark = bool(key) and not (design_id or "").startswith("name:")
        # The design's folder and history file; the folder check may move them.
        folder_state: Dict[str, Any] = {"folder": design_folder, "history": history_file}

        def network(auth: Optional[GitAuth]) -> Optional[Dict[str, Any]]:
            confirmed_reuse = False
            bootstrapped = False
            branch = override or target or generated_name
            for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
                step("Checking GitHub…")
                default, heads = remote_branches(repo_path, auth)

                if not heads:
                    # Completely empty repository: give it a first commit on
                    # main, so it has a default branch, plus .gitattributes.
                    step("Setting up the empty repository on GitHub…")
                    init_commit = _build_commit(
                        repo_path,
                        None,
                        [],
                        {".gitattributes": GITATTRIBUTES_CONTENT.encode("utf-8")},
                        "Initialize repository for Fusion exports",
                        identity,
                    )
                    state.update(phase="bootstrapping", branch=BOOTSTRAP_BRANCH, commit=init_commit)
                    proc = git_run(
                        repo_path,
                        "push",
                        "origin",
                        f"{init_commit}:refs/heads/{BOOTSTRAP_BRANCH}",
                        check=False,
                        auth=auth,
                        network=True,
                    )
                    if proc.returncode != 0 and not _is_push_rejection(proc.stderr or proc.stdout):
                        raise GitError(f"Could not set up the empty repository:\n{proc.stderr or proc.stdout}")
                    bootstrapped = bootstrapped or proc.returncode == 0
                    if proc.returncode == 0:
                        state["bootstrapped"] = True  # a later cancel must still say so
                    continue  # look again: someone else may have set it up meanwhile

                if mode == MODE_SINGLE:
                    branch = target or default or BOOTSTRAP_BRANCH
                    reused = branch in heads
                else:
                    if override:
                        branch = override
                        reused = branch in heads
                        if reused and not confirmed_reuse:
                            if branch == default:
                                question = (
                                    f"'{branch}' is this repository's main branch: the one everyone sees "
                                    "first on GitHub.\n\nAdd this export directly to it?"
                                )
                            else:
                                question = (
                                    f"Branch '{branch}' already exists on GitHub.\n\n"
                                    "Add this export as a new commit on that branch?"
                                )
                            if not ui.confirm(question):
                                return {"cancelled": True, "repository_initialized": bootstrapped}
                            confirmed_reuse = True
                    else:
                        branch = generated_name
                        suffix = 2
                        while branch in heads:
                            branch = f"{generated_name}-{suffix}"
                            suffix += 1
                        reused = False

                base_branch = branch if branch in heads else default
                base = heads.get(base_branch) if base_branch else None
                if base and base_branch:
                    base = _ensure_commit_available(repo_path, base_branch, base, auth)

                if key and relocate and folder_state["folder"]:
                    chosen = _choose_design_folder(repo_path, base, folder_state["folder"], key, relocate)
                    if chosen != folder_state["folder"]:
                        moved_exports, moved_history = relocate(chosen)
                        files[:] = [(src, normalize_repo_path(rel)) for src, rel in moved_exports]
                        folder_state.update(folder=chosen, history=moved_history)
                        if logger:
                            logger.info("Design folder on GitHub: '%s'", chosen)
                history_path = folder_state["history"]

                step("Preparing the commit…")
                message = (
                    (commit_msg_template or "Design update: {filename}")
                    .replace("{filename}", design_name)
                    .replace("{branch}", branch)
                    .replace("{timestamp}", timestamp_str)
                    # Last, so placeholders typed in the note stay as typed.
                    .replace("{message}", single_line(commit_text or "") or "Design update")
                )
                extra: Dict[str, bytes] = {}
                if history_path:
                    rel_history = normalize_repo_path(history_path)
                    existing = _read_blob(repo_path, base, rel_history) or b""
                    entry = _history_entry(
                        design_name, branch, message, [rel for _, rel in files], when, history_notes,
                        fusion_version,
                    )
                    header = f"# {history_title}\n\n" if history_title else "# Changelog\n\n"
                    if not existing and legacy_history_file and _read_blob(
                        repo_path, base, normalize_repo_path(legacy_history_file)
                    ) is not None:
                        # The repository has history written by an older
                        # version in one shared file; point to it, never move it.
                        header += (
                            f"Earlier pushes are listed in `{legacy_history_file}` at the repository "
                            "root, written by versions before 0.5.0.\n\n"
                        )
                    updated = _updated_history(existing, entry, header)
                    extra[rel_history] = _with_marker(updated, key) if mark else updated
                files[:] = _existing_spelling(repo_path, base, files)
                commit = _build_commit(repo_path, base, files, extra, message, identity)

                step("Pushing to GitHub…")
                state.update(phase="pushing", branch=branch, commit=commit, base=base)
                try:
                    proc = git_run(
                        repo_path,
                        "push",
                        "origin",
                        f"{commit}:refs/heads/{branch}",
                        check=False,
                        auth=auth,
                        network=True,
                    )
                except GitTimeoutError as timeout:
                    # The push may or may not have reached GitHub: ask it.
                    outcome = _cancelled_result(repo_path, state, auth, logger)
                    if outcome.get("published"):
                        proc = subprocess.CompletedProcess([GIT_EXE, "push"], 0, "", "")
                    elif outcome.get("uncertain"):
                        raise GitError(
                            f"{timeout}\n\nIt couldn't be confirmed whether this backup arrived. Look at "
                            "the repository on GitHub before backing up again."
                        ) from timeout
                    else:
                        raise GitError(f"{timeout}\n\nGitHub didn't receive this backup; nothing on GitHub "
                                       "was changed.") from timeout
                if proc.returncode == 0:
                    state["phase"] = "done"
                    return {
                        "branch": branch,
                        "commit": commit,
                        "base": base,
                        "base_branch": base_branch,
                        "default_branch": default,
                        "mode": mode,
                        "timestamp": timestamp_str,
                        "reused_branch": reused,
                        "files": [rel for _, rel in files],
                        "attempts": attempt,
                        "bootstrapped": bootstrapped,
                        "design_folder": folder_state["folder"],
                        "history_file": history_path,
                    }
                output = proc.stderr or proc.stdout or ""
                if not _is_push_rejection(output):
                    raise GitError(f"git push failed. Nothing on GitHub was changed.\n\nDetails:\n{output}")
                if logger:
                    logger.info("Push to '%s' rejected (attempt %d); rebuilding on the new tip.", branch, attempt)

            ui.error(
                f"GitHub kept receiving other changes on '{branch}' while this export was being "
                f"pushed ({MAX_PUSH_ATTEMPTS} attempts). Nothing on GitHub was changed. "
                "Try again in a moment."
            )
            return None

        with token_session(repo_path, origin_url, pat_credentials) as auth:
            try:
                with cancel_scope(cancel):
                    return network(auth)
            except GitCancelled:
                return _cancelled_result(repo_path, state, auth, logger)
            finally:
                # Tidying up must never turn a finished push into a reported
                # failure (S7 correctness review).
                try:
                    git_run(repo_path, "update-ref", "-d", _BASE_REF, check=False)
                except (GitError, OSError) as exc:
                    if logger:
                        logger.warning("Couldn't remove the temporary reference %s: %s", _BASE_REF, exc)
    except (GitError, ValueError, OSError) as exc:
        secrets = (token_secrets(pat_credentials.get("token", ""), pat_credentials.get("username", ""))
                   if pat_credentials else [])
        msg = redact_secrets(f"Push failed:\n{exc}", secrets)
        ui.error(msg)
        if logger:
            logger.error(msg, exc_info=True)
        return None


__all__ = [
    "VERSION",
    "IS_WINDOWS",
    "GIT_EXE",
    "TIMEOUTS",
    "SIZE_WARN_BYTES",
    "SIZE_BLOCK_BYTES",
    "export_size_check",
    "MODE_SNAPSHOT",
    "MODE_SINGLE",
    "GitUI",
    "GitError",
    "GitTimeoutError",
    "GitCancelled",
    "cancel_scope",
    "find_git",
    "git_candidates",
    "sanitize_branch_name",
    "generate_branch_name",
    "is_valid_branch_name",
    "normalize_repo_path",
    "remote_branches",
    "git_run",
    "git_output",
    "git_available",
    "GitAuth",
    "token_auth",
    "redact_secrets",
    "url_has_embedded_secret",
    "push_export",
    "branch_name_problem",
    "check_connection",
    "design_key",
    "history_owner",
    "token_session",
]
