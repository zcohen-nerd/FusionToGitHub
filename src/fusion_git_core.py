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

import logging
import os
import posixpath
import re
import shutil
import signal
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

VERSION = "0.4.0"
IS_WINDOWS = os.name == "nt"
GIT_EXE = shutil.which("git") or (r"C:\Program Files\Git\bin\git.exe" if IS_WINDOWS else "git")

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
    env: Optional[Dict[str, str]] = None,
    network: bool = False,
    timeout: Optional[float] = None,
    input_bytes: Optional[bytes] = None,
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
    if env:
        env_vars.update(env)

    cmd = [GIT_EXE]
    if network:
        # Abort a transfer that stays below 1 KB/s for a minute.
        cmd += ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60"]
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
    try:
        out, err = proc.communicate(input_bytes, timeout=limit)
    except subprocess.TimeoutExpired:
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
) -> subprocess.CompletedProcess:
    """Run git and return its result with stdout/stderr decoded as UTF-8.

    Set *network* for commands that talk to the remote (clone, fetch, push,
    ls-remote): they get the longer timeout and stall detection. Raises
    GitTimeoutError when the timeout is hit and, when *check* is true,
    GitError for a non-zero exit.
    """
    returncode, out, err = _run_git_bytes(
        repo_path,
        args,
        env=env,
        network=network,
        timeout=timeout,
        input_bytes=input_text.encode("utf-8") if input_text is not None else None,
    )
    # UTF-8 with replacement: decoding with the Windows code page could fail
    # on names like "Łukasz" and silently lose the output (audit REL-03).
    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if check and returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{stderr or stdout}")
    return subprocess.CompletedProcess([GIT_EXE, *args], returncode, stdout, stderr)


def git_output(repo_path: Optional[str], *args: str, env: Optional[Dict[str, str]] = None, network: bool = False) -> str:
    return (git_run(repo_path, *args, check=True, env=env, network=network).stdout or "").strip()


def _git_bytes(repo_path: str, *args: str, env: Optional[Dict[str, str]] = None) -> bytes:
    returncode, out, err = _run_git_bytes(repo_path, args, env=env)
    if returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{err.decode('utf-8', errors='replace')}")
    return out


def git_available() -> bool:
    try:
        return git_run(None, "--version", check=False, timeout=15).returncode == 0
    except Exception:
        return False


@contextmanager
def git_askpass_env(username: str, token: str):
    """Yield env vars that let git authenticate through a temp askpass script.

    The script itself contains no credentials: it echoes environment
    variables that exist only in the git subprocess environment, so the
    token is never written to disk (and needs no shell escaping).
    """
    if not token:
        yield {}
        return

    temp_dir = tempfile.mkdtemp(prefix="fusion_git_auth_")
    script_path = os.path.join(
        temp_dir,
        "askpass.bat" if IS_WINDOWS else "askpass.sh",
    )

    if IS_WINDOWS:
        # The prompt kind is decided by an anchored prefix test, not a
        # substring search: a password prompt like
        # "Password for 'https://myusername@github.com':" contains the word
        # "username" and must still yield the token. Delayed expansion
        # (!VAR!) keeps special characters in the values from being
        # re-parsed by cmd; 'if defined' avoids the literal '!VAR!' output
        # cmd produces for undefined delayed variables.
        script_contents = (
            "@echo off\n"
            "setlocal EnableDelayedExpansion\n"
            'set "PROMPT_ARG=%~1"\n'
            'if /I "!PROMPT_ARG:~0,12!"=="Username for" (\n'
            "    if defined FUSION_GIT_ASKPASS_USERNAME (\n"
            "        echo(!FUSION_GIT_ASKPASS_USERNAME!\n"
            "    ) else (\n"
            "        echo(\n"
            "    )\n"
            ") else (\n"
            "    echo(!FUSION_GIT_ASKPASS_TOKEN!\n"
            ")\n"
        )
    else:
        # Same anchored prefix test as the Windows script (see above).
        script_contents = (
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  [Uu]\"sername for \"* ) printf '%s\\n' \"$FUSION_GIT_ASKPASS_USERNAME\" ;;\n"
            "  * ) printf '%s\\n' \"$FUSION_GIT_ASKPASS_TOKEN\" ;;\n"
            "esac\n"
        )

    with open(script_path, "w", encoding="utf-8") as askpass_file:
        askpass_file.write(script_contents)
    if not IS_WINDOWS:
        os.chmod(script_path, 0o700)

    env_map = {
        "GIT_ASKPASS": script_path,
        "GIT_TERMINAL_PROMPT": "0",
        "FUSION_GIT_ASKPASS_USERNAME": username or "",
        "FUSION_GIT_ASKPASS_TOKEN": token,
    }

    try:
        yield env_map
    finally:
        try:
            os.remove(script_path)
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


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
    repo_path: str, env: Optional[Dict[str, str]] = None
) -> Tuple[Optional[str], Dict[str, str]]:
    """Return (default branch or None, {branch: tip sha}) as GitHub reports them now."""
    listing = git_output(
        repo_path, "ls-remote", "--symref", "origin", "HEAD", "refs/heads/*", env=env, network=True
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
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/") :]] = sha.strip()
    if default not in heads:
        default = next((b for b in ("main", "master") if b in heads), None) or (
            sorted(heads)[0] if heads else None
        )
    return default, heads


def _ensure_commit_available(repo_path: str, branch: str, sha: str, env: Optional[Dict[str, str]]) -> str:
    """Make sure the branch tip is in the local object store; return the tip to build on."""
    if git_run(repo_path, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0:
        return sha
    git_run(
        repo_path, "fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{branch}:{_BASE_REF}", env=env, network=True
    )
    # The branch may have moved since it was listed; build on what was fetched.
    return git_output(repo_path, "rev-parse", "--verify", f"{_BASE_REF}^{{commit}}")


def _history_entry(
    design_name: str, branch: str, message: str, rel_paths: Sequence[str], when: datetime
) -> str:
    lines = [
        f"## {when.strftime('%Y-%m-%d %H:%M:%S')} - {design_name}",
        f"- **Branch:** `{branch}`",
        f'- **Commit Message:** "{message}"',
    ]
    if rel_paths:
        lines.append("- **Files Updated:**")
        lines.extend(f"  - `{rel}`" for rel in rel_paths)
    lines.append("\n---\n")
    return "\n".join(lines) + "\n"


def _updated_history(existing: bytes, entry: str) -> bytes:
    """Prepend *entry* to an existing history file, keeping its bytes intact."""
    header = b"# Changelog\n\n"
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    body = existing
    for candidate in (header, header.replace(b"\n", b"\r\n")):
        if body.startswith(candidate):
            body = body[len(candidate) :]
            break
    new_entry = entry.encode("utf-8").replace(b"\n", newline)
    return header.replace(b"\n", newline) + new_entry + body


def _build_commit(
    repo_path: str,
    parent: Optional[str],
    files: Sequence[Tuple[str, str]],
    extra_blobs: Dict[str, bytes],
    message: str,
) -> str:
    """Create a commit = *parent*'s tree + *files* + *extra_blobs*, without touching the user's index."""
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
            return git_run(repo_path, *args, input_text=message).stdout.strip()
        except GitError as exc:
            if "Please tell me who you are" in str(exc) or "unable to auto-detect email" in str(exc):
                raise GitError(
                    "Git doesn't know your name and email yet, so it can't sign the commit. "
                    "Set them (git config user.name / user.email) and try again."
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
) -> Optional[Dict[str, Any]]:
    """Commit *exports* on top of GitHub's branch tip and push it, without touching the checkout.

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
            size = os.path.getsize(source_path)
            if size == 0:
                raise ValueError(f"The exported file '{rel}' is empty; nothing was pushed.")
            if size >= SIZE_BLOCK_BYTES:
                ui.error(
                    f"'{rel}' is {size / 1048576:.0f} MB. GitHub rejects files of 100 MB or more, "
                    "so nothing was pushed.\nUntick that format, or lower the STL mesh refinement, "
                    "and try again."
                )
                return None
        large = [(rel, os.path.getsize(src)) for src, rel in files if os.path.getsize(src) >= SIZE_WARN_BYTES]
        if large:
            listing = "\n".join(f"  {rel}: {size / 1048576:.0f} MB" for rel, size in large)
            if not ui.confirm(
                f"These exports are large:\n{listing}\n\nGitHub warns about files over 50 MB, and "
                "every version is kept forever, so the repository will grow quickly.\n\nPush anyway?"
            ):
                return {"cancelled": True}

        if git_run(repo_path, "rev-parse", "--git-dir", check=False).returncode != 0:
            raise GitError(f"'{repo_path}' is not a Git repository.")
        if "origin" not in git_output(repo_path, "remote").splitlines():
            ui.error("This repository has no 'origin' remote, so there is nowhere to push.")
            return None

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

        def network(git_env: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
            confirmed_reuse = False
            bootstrapped = False
            branch = override or target or generated_name
            for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
                step("Checking GitHub…")
                default, heads = remote_branches(repo_path, git_env)

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
                    )
                    proc = git_run(
                        repo_path,
                        "push",
                        "origin",
                        f"{init_commit}:refs/heads/{BOOTSTRAP_BRANCH}",
                        check=False,
                        env=git_env,
                        network=True,
                    )
                    if proc.returncode != 0 and not _is_push_rejection(proc.stderr or proc.stdout):
                        raise GitError(f"Could not set up the empty repository:\n{proc.stderr or proc.stdout}")
                    bootstrapped = bootstrapped or proc.returncode == 0
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
                                return {"cancelled": True}
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
                    base = _ensure_commit_available(repo_path, base_branch, base, git_env)

                step("Preparing the commit…")
                message = (
                    (commit_msg_template or "Design update: {filename}")
                    .replace("{filename}", design_name)
                    .replace("{branch}", branch)
                    .replace("{timestamp}", timestamp_str)
                )
                extra: Dict[str, bytes] = {}
                if history_file:
                    rel_history = normalize_repo_path(history_file)
                    existing = _read_blob(repo_path, base, rel_history) or b""
                    entry = _history_entry(design_name, branch, message, [rel for _, rel in files], when)
                    extra[rel_history] = _updated_history(existing, entry)
                commit = _build_commit(repo_path, base, files, extra, message)

                step("Pushing to GitHub…")
                proc = git_run(
                    repo_path,
                    "push",
                    "origin",
                    f"{commit}:refs/heads/{branch}",
                    check=False,
                    env=git_env,
                    network=True,
                )
                if proc.returncode == 0:
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

        try:
            if pat_credentials and pat_credentials.get("token"):
                with git_askpass_env(pat_credentials.get("username", ""), pat_credentials["token"]) as env_map:
                    return network(env_map)
            return network(None)
        finally:
            git_run(repo_path, "update-ref", "-d", _BASE_REF, check=False)
    except (GitError, ValueError, OSError) as exc:
        msg = f"Push failed:\n{exc}"
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
    "MODE_SNAPSHOT",
    "MODE_SINGLE",
    "GitUI",
    "GitError",
    "GitTimeoutError",
    "sanitize_branch_name",
    "generate_branch_name",
    "is_valid_branch_name",
    "normalize_repo_path",
    "remote_branches",
    "git_run",
    "git_output",
    "git_available",
    "git_askpass_env",
    "push_export",
]
