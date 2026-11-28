"""Check My Setup: what this computer and a saved repository need before a backup (audit UX-07).

No Fusion dependency. The local checks are quick (they read Git's version
and settings and the repository folder) and run on Fusion's main thread.
The connection test talks to GitHub, so it runs on the background push
thread like a push does (``ConnectionTest`` has the ``execute`` method the
push worker calls) and changes nothing anywhere: it only lists the
repository's branches.

Every result has a plain-language title and, when something needs doing,
a next step. Statuses are written as words ("OK", "Problem"), never only
as symbols or colours.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import fusion_git_core as git_core
from .dialog_helpers import synced_folder_service
from .error_catalog import classify

# The oldest Git the add-in is meant for. Older versions lack features it
# relies on (for example GIT_TRACE_REDACT and per-command credential
# settings) and are not tested; they get a warning, not a refusal.
MIN_GIT_VERSION: Tuple[int, int] = (2, 30)
CONNECTION_TIMEOUT_SECONDS = 120
GIT_DOWNLOAD_URL = "https://git-scm.com/downloads"
GCM_URL = "https://github.com/git-ecosystem/git-credential-manager#readme"

OK, WARN, PROBLEM, INFO = "ok", "warn", "problem", "info"
STATUS_LABELS = {OK: "OK", WARN: "Check", PROBLEM: "Problem", INFO: "Note"}


@dataclass
class Check:
    status: str
    title: str
    detail: str = ""
    next_step: str = ""

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


def parse_git_version(text: str) -> Optional[Tuple[int, ...]]:
    """(2, 47, 1) from "git version 2.47.1.windows.1"; None if there is no version."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def _config(git, repo_path: Optional[str], *args: str) -> str:
    try:
        proc = git.git_run(repo_path, "config", *args, check=False, timeout=15)
    except git.GitError:
        return ""
    return (proc.stdout or "").strip() if proc.returncode == 0 else ""


def check_git(git=git_core) -> Check:
    try:
        proc = git.git_run(None, "--version", check=False, timeout=15)
        text = (proc.stdout or "").strip() if proc.returncode == 0 else ""
    except (git.GitError, OSError):
        text = ""
    version = parse_git_version(text)
    if not version:
        return Check(PROBLEM, "Git was not found on this computer.",
                     "The add-in uses Git to send your designs to GitHub.",
                     f"Install Git from {GIT_DOWNLOAD_URL} (on Windows, the default options are fine; on macOS, "
                     "use Homebrew or Xcode Command Line Tools), restart Fusion, then check again.")
    shown = ".".join(str(part) for part in version)
    where = getattr(git, "GIT_EXE", "git")
    if version[:2] < MIN_GIT_VERSION:
        minimum = ".".join(str(part) for part in MIN_GIT_VERSION)
        return Check(WARN, f"Git {shown} is older than this add-in is tested with.",
                     f"Found at {where}. Version {minimum} or newer is recommended.",
                     f"Update Git from {GIT_DOWNLOAD_URL}, then restart Fusion.")
    return Check(OK, f"Git {shown} is installed.", f"Found at {where}.")


def check_identity(git=git_core, profile: Optional[Dict[str, Any]] = None,
                   repo_path: Optional[str] = None) -> Check:
    saved = (profile or {}).get("gitIdentity") or {}
    if saved.get("name") and saved.get("email"):
        return Check(OK, "Your name and email for backups are saved for this repository.",
                     f"{saved['name']} <{saved['email']}>")
    name = _config(git, repo_path, "--get", "user.name")
    email = _config(git, repo_path, "--get", "user.email")
    if name and email:
        return Check(OK, "Git knows your name and email.", f"{name} <{email}>")
    return Check(INFO, "Git doesn't know your name and email yet.",
                 "Each backup is labelled with them.",
                 "Nothing to do now: the add-in asks for them once, at your first backup.")


def check_sign_in(git=git_core, profile: Optional[Dict[str, Any]] = None, token_stored: bool = False,
                  is_windows: bool = git_core.IS_WINDOWS) -> Check:
    if (profile or {}).get("useStoredPat"):
        if token_stored:
            return Check(OK, "This repository uses a stored token to sign in to GitHub.")
        return Check(PROBLEM, "This repository is set to use a stored token, but none is stored.",
                     next_step="Store one with Advanced → Manage Token…, or untick Use Stored Token.")
    helpers = _config(git, None, "--get-all", "credential.helper").lower()
    if "manager" in helpers:
        return Check(OK, "Git Credential Manager will handle GitHub sign-in.",
                     "The first time, a GitHub sign-in window opens in your browser.")
    if not is_windows and "osxkeychain" in helpers:
        return Check(WARN, "Git can't show a GitHub sign-in window here.",
                     "macOS's keychain helper can reuse a saved sign-in but can't ask for a new one from "
                     "inside Fusion.",
                     f"Install Git Credential Manager ({GCM_URL}), then check again.")
    if helpers:
        return Check(INFO, "Git uses a sign-in helper this add-in doesn't recognise.",
                     f"credential.helper = {helpers.splitlines()[0]}",
                     "If the connection test below succeeds, nothing needs doing.")
    if is_windows:
        return Check(WARN, "No GitHub sign-in helper is set up for Git.",
                     "Without one, Git can't ask you to sign in.",
                     "Reinstall Git for Windows with its default options (they include Git Credential "
                     "Manager), or store a token with Advanced → Manage Token….")
    return Check(WARN, "No GitHub sign-in helper is set up for Git.",
                 next_step=f"Install Git Credential Manager ({GCM_URL}), then check again.")


def check_repository(git, name: str, profile: Dict[str, Any], token_problem: str = "") -> List[Check]:
    """Checks of a saved repository's folder and settings (no network)."""
    path = os.path.expanduser(profile.get("path") or "")
    if not path or not os.path.isdir(path):
        return [Check(PROBLEM, f"The local folder for '{name}' doesn't exist.", path,
                      "Choose its folder again with Edit Repository…, or remove the entry and set it up again.")]
    if not os.path.isdir(os.path.join(path, ".git")):
        return [Check(PROBLEM, f"The local folder for '{name}' isn't a Git repository folder.", path,
                      "Choose the right folder with Edit Repository…, or set the repository up again.")]
    checks = [Check(OK, f"The local folder for '{name}' is ready.", path)]
    origin = _config(git, path, "--get", "remote.origin.url")
    saved = profile.get("url") or ""
    if not origin:
        checks.append(Check(PROBLEM, "The local folder isn't connected to a GitHub repository.",
                            next_step="Set the GitHub address with Edit Repository… and choose Yes when asked "
                                      "to update the folder."))
    elif saved and git._repository_key(origin) != git._repository_key(saved):
        checks.append(Check(WARN, "The folder's GitHub address differs from the saved one.",
                            f"Folder: {git.redact_secrets(origin)}\nSaved: {git.redact_secrets(saved)}",
                            "Backups go to the folder's address. Use Edit Repository… to make them match."))
    service = synced_folder_service(path)
    if service:
        checks.append(Check(INFO, f"The folder is inside {service}.",
                            "Sync apps can lock or duplicate Git's files while a backup runs.",
                            "A folder outside it is safer; your designs are on GitHub either way."))
    if token_problem:
        checks.append(Check(PROBLEM, "The stored token won't be used with this folder.", token_problem))
    return checks


def local_checks(
    profile_name: Optional[str],
    profile: Optional[Dict[str, Any]],
    *,
    token_stored: bool = False,
    token_problem: str = "",
    git=git_core,
) -> List[Check]:
    """Everything that can be checked without the network, in the order to read them."""
    git_check = check_git(git)
    checks = [git_check]
    if git_check.status == PROBLEM:
        return checks  # nothing else can be checked without Git
    repo_path = os.path.expanduser(profile.get("path") or "") if profile else None
    if repo_path and not os.path.isdir(os.path.join(repo_path, ".git")):
        repo_path = None
    checks.append(check_identity(git, profile, repo_path))
    checks.append(check_sign_in(git, profile, token_stored))
    if profile_name and profile is not None:
        checks.extend(check_repository(git, profile_name, profile, token_problem))
    return checks


def can_test_connection(checks: Sequence[Check]) -> bool:
    return not any(c.status == PROBLEM for c in checks)


class ConnectionTest:
    """The connection test, run by push_worker.PushWorker on its background thread."""

    def __init__(self, repo_path: str, pat_credentials: Optional[Dict[str, str]] = None,
                 timeout: float = CONNECTION_TIMEOUT_SECONDS, git=git_core):
        self.repo_path = repo_path
        self.pat_credentials = pat_credentials
        self.timeout = timeout
        self.git = git

    def execute(self, plan: Any, ui: Any, on_step: Optional[Callable[[str], None]] = None,
                cancel=None) -> Dict[str, Any]:
        if on_step:
            on_step("Connecting to GitHub… (a sign-in window may open)")
        result = self.git.check_connection(self.repo_path, self.pat_credentials, cancel=cancel,
                                           timeout=self.timeout)
        return dict(result, kind="setup_check")


def connection_check(result: Optional[Dict[str, Any]]) -> Check:
    """The connection test's result as a Check."""
    result = result or {}
    if result.get("cancelled"):
        return Check(INFO, "The connection test was cancelled.")
    if result.get("ok"):
        if result.get("empty"):
            return Check(OK, "GitHub accepted the sign-in. The repository is empty.",
                         "Your first backup sets it up (a 'main' branch with your design's folder).")
        branch = result.get("default_branch") or "main"
        return Check(OK, "GitHub accepted the sign-in and the repository is reachable.",
                     f"Its main branch is '{branch}'.")
    error = result.get("error") or "No details."
    explanation = classify(error)
    if explanation is None:
        return Check(PROBLEM, "The connection test failed.", error,
                     "Check the address and your internet connection, then try again.")
    return Check(PROBLEM, explanation.headline, error, explanation.next_step)


def format_report(checks: Sequence[Any], heading: str = "Check My Setup") -> str:
    """The checks as text for a message box: one block per check, status in words."""
    items = [c if isinstance(c, Check) else Check(**c) for c in checks]
    problems = sum(1 for c in items if c.status == PROBLEM)
    warnings = sum(1 for c in items if c.status == WARN)
    if problems:
        summary = f"{problems} problem{'s' if problems != 1 else ''} to fix before backing up."
    elif warnings:
        summary = f"Ready, with {warnings} thing{'s' if warnings != 1 else ''} worth checking."
    else:
        summary = "Everything needed for a backup is in place."
    lines = [heading, summary, ""]
    for check in items:
        lines.append(f"[{STATUS_LABELS.get(check.status, check.status)}] {check.title}")
        if check.detail:
            lines.extend(f"    {line}" for line in check.detail.splitlines())
        if check.next_step:
            lines.append(f"    Next: {check.next_step}")
    return "\n".join(lines)


def has_problem(checks: Sequence[Any]) -> bool:
    return any((c.status if isinstance(c, Check) else c.get("status")) == PROBLEM for c in checks)


__all__ = [
    "Check",
    "ConnectionTest",
    "MIN_GIT_VERSION",
    "can_test_connection",
    "check_git",
    "check_identity",
    "check_repository",
    "check_sign_in",
    "connection_check",
    "format_report",
    "has_problem",
    "local_checks",
    "parse_git_version",
]
