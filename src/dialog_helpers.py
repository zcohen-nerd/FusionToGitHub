"""Pure helper functions extracted from the Fusion dialog handler.

These functions have no Fusion 360 API dependencies and can be tested
independently outside the add-in runtime.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional


# Matches GitHub browser URLs (optionally scheme-less), capturing owner and
# repo while tolerating extra path segments (/tree/..., /blob/...), query
# strings, and fragments.
_GITHUB_WEB_URL_RE = re.compile(
    r"^(?:https://)?(?:www\.)?github\.com/([^/?#]+)/([^/?#]+?)(?:\.git)?(?:[/?#].*)?$"
)


def convert_github_url(url: str) -> str:
    """Convert a GitHub browser URL to the canonical Git clone URL.

    Handles trailing slashes, query params, fragments, extra path segments
    such as ``/tree/main`` or ``/blob/...``, and scheme-less forms like
    ``github.com/user/repo``.  Anything unrecognised — including partially
    typed values — is returned unchanged rather than guessed at.
    """
    url = (url or "").strip()
    if not url:
        return url

    # The pattern tolerates an existing .git suffix, so complete clone URLs
    # come back unchanged while scheme-less ones still gain https://.
    match = _GITHUB_WEB_URL_RE.match(url)
    if match:
        user, repo = match.groups()
        return f"https://github.com/{user}/{repo}.git"

    return url


def derive_repo_name_from_url(url: str) -> str:
    """Best-effort repository name from a Git URL; '' when none can be found.

    Works for https URLs and scp-like forms (``git@host:user/repo.git``).
    """
    candidate = (url or "").strip().rstrip("/")
    if not candidate:
        return ""
    if candidate.endswith(".git"):
        candidate = candidate[: -len(".git")].rstrip("/")
    if "/" in candidate:
        candidate = candidate.rsplit("/", 1)[-1]
    if ":" in candidate:
        candidate = candidate.rsplit(":", 1)[-1]
    return candidate


def validate_repo_inputs(
    selection_name: str,
    raw_path: str,
    git_url_val: str,
    add_new_option: str,
) -> dict:
    """Validate repository path and Git URL inputs.

    Returns a dict with keys ``messages``, ``ok``, ``path``, and
    ``has_git_dir``.  ``messages`` maps ``"path"`` and ``"git"`` to
    ``(text, severity)`` tuples.
    """
    messages: dict = {"path": ("", "info"), "git": ("", "info")}
    ok = True

    def set_msg(field: str, text: str, severity: str = "info"):
        messages[field] = (text, severity)

    expanded = raw_path.strip()
    if expanded:
        expanded = os.path.expanduser(expanded)
    normalized_path = os.path.abspath(expanded) if expanded else ""

    git_dir_exists = (
        os.path.isdir(os.path.join(normalized_path, ".git"))
        if normalized_path
        else False
    )
    has_git_url = bool(git_url_val.strip())

    if not normalized_path:
        set_msg("path", "⚠️ Provide a repository path.", "error")
        ok = False
    elif not os.path.isabs(normalized_path):
        set_msg("path", "⚠️ Path must be absolute.", "error")
        ok = False
    elif not os.path.exists(normalized_path):
        if selection_name == add_new_option and has_git_url:
            set_msg(
                "path",
                "ℹ️ Path will be created when cloning the remote repository.",
                "info",
            )
        else:
            set_msg("path", "❌ Path does not exist.", "error")
            ok = False
    elif not os.path.isdir(normalized_path):
        set_msg("path", "❌ Path is not a directory.", "error")
        ok = False
    else:
        if git_dir_exists:
            set_msg("path", "✅ Repository path looks good.", "success")
        elif selection_name == add_new_option and has_git_url:
            set_msg(
                "path",
                "ℹ️ Git repository will be initialized here.",
                "info",
            )
        else:
            set_msg(
                "path",
                "❌ Missing .git directory at this path.",
                "error",
            )
            ok = False

    if selection_name == add_new_option:
        if has_git_url:
            pattern = r"^(https://|git@|ssh://).+\.git$"
            if re.match(pattern, git_url_val.strip()):
                set_msg("git", "✅ Git URL format looks valid.", "success")
            else:
                set_msg(
                    "git",
                    "❌ Please paste a GitHub repository URL"
                    " (e.g., https://github.com/user/repo)",
                    "error",
                )
                ok = False
        else:
            if git_dir_exists:
                set_msg(
                    "git",
                    "✅ Local repository detected (no remote URL provided).",
                    "success",
                )
            else:
                set_msg(
                    "git",
                    "⚠️ Provide a Git URL or choose a folder"
                    " that already contains a .git directory.",
                    "error",
                )
                ok = False
    else:
        set_msg("git", "", "info")

    return {
        "messages": messages,
        "ok": ok,
        "path": normalized_path,
        "has_git_dir": git_dir_exists,
    }


def normalize_export_subfolder(raw: str) -> str:
    """Validate and normalise an export subfolder value or template.

    Accepts forward or back slashes; rejects absolute paths, ``..``/``.``
    segments, and characters that are invalid in folder names. Returns the
    cleaned relative path ('' when blank). ``{filename}`` and
    ``{timestamp}`` placeholders pass through untouched — they are filled
    by :func:`expand_export_subfolder` at export time.
    """
    value = (raw or "").strip().replace("\\", "/")
    if not value:
        return ""
    if value.startswith("/"):
        raise ValueError("Export subfolder must be relative (no leading slash).")
    parts = [segment.strip() for segment in value.split("/") if segment.strip()]
    if not parts:
        return ""
    invalid = {"..", "."}
    for segment in parts:
        if segment in invalid:
            raise ValueError("Export subfolder cannot contain '..' or '.' segments.")
        if re.search(r'[<>:"\\|?*]', segment):
            raise ValueError(f"Invalid characters in subfolder segment '{segment}'.")
    return "/".join(parts)


def expand_export_subfolder(
    template: str,
    design_name: str,
    timestamp: Optional[str] = None,
) -> str:
    """Fill ``{filename}`` and ``{timestamp}`` placeholders in a subfolder.

    Returns the normalised, expanded relative path ('' when the template is
    blank). Raises ``ValueError`` if the expansion produces an invalid path.
    """
    if not template:
        return ""
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    expanded = (
        template.replace("{filename}", design_name or "Design").replace("{timestamp}", ts)
    )
    return normalize_export_subfolder(expanded)


def ensure_export_subfolder_exists(repo_path: str, relative_subfolder: str) -> str:
    """Create the export subfolder inside the repo and return its path.

    Raises ``ValueError`` if the subfolder would resolve outside the
    repository root.
    """
    if not relative_subfolder:
        return repo_path
    root = os.path.normpath(repo_path)
    dest = os.path.normpath(os.path.join(root, relative_subfolder))
    # Separator-aware containment check: a bare prefix test would accept
    # sibling paths like "C:\repo-evil" for root "C:\repo".
    if dest != root and not dest.startswith(root + os.sep):
        raise ValueError("Export subfolder resolves outside the repository root.")
    os.makedirs(dest, exist_ok=True)
    return dest


def default_path_for_new_repo(
    proposed_name: str,
    base_dir: str,
    safe_base_fn,
) -> str:
    """Build a default local path for a new repository.

    *safe_base_fn* is expected to be ``_safe_base`` (or equivalent) –
    passed explicitly so this module stays free of Fusion-specific
    helpers.
    """
    if not proposed_name:
        return os.path.join(base_dir, "NewRepo")
    sanitized = safe_base_fn(proposed_name) or proposed_name
    return os.path.join(base_dir, sanitized)


def setup_new_repository(
    repo_name: str,
    local_path: str,
    git_url: str,
    git_fn,
    *,
    logger=None,
) -> Optional[str]:
    """Prepare a local Git repo connected to ``origin``.

    When *git_url* is provided and *local_path* is missing or empty, the
    remote is cloned so the local repository starts with the remote's
    history. Otherwise the folder is initialised in place and ``origin``
    is configured. Either way the repository ends up with at least one
    commit, because later branch/stash operations need a born HEAD.

    *git_fn* must be a callable with the same signature as
    ``_git(repo_path, *args, check=…)``.

    Returns ``None`` on success or an error message string on failure.
    """
    git_dir_path = os.path.join(local_path, ".git")
    has_git_dir = os.path.isdir(git_dir_path)
    dir_is_empty = not os.path.exists(local_path) or not os.listdir(local_path)

    if git_url and dir_is_empty and not has_git_dir:
        parent_dir = os.path.dirname(local_path) or "."
        os.makedirs(parent_dir, exist_ok=True)
        try:
            git_fn(parent_dir, "clone", git_url, local_path)
            if logger:
                logger.info("Cloned %s into %s", git_url, local_path)
        except Exception as exc:
            return f"Failed to clone repository:\n{exc}"
    else:
        if not os.path.exists(local_path):
            os.makedirs(local_path, exist_ok=True)

        if not has_git_dir:
            try:
                git_fn(local_path, "init")
                if logger:
                    logger.info("Initialized Git repository in %s", local_path)
            except Exception as exc:
                return f"Failed to initialize Git repository:\n{exc}"

        if git_url:
            try:
                result = git_fn(
                    local_path, "remote", "get-url",
                    "origin", check=False,
                )
                if result.returncode == 0:
                    git_fn(local_path, "remote", "set-url", "origin", git_url)
                    if logger:
                        logger.info("Updated remote 'origin' to %s", git_url)
                else:
                    git_fn(local_path, "remote", "add", "origin", git_url)
                    if logger:
                        logger.info("Added remote 'origin': %s", git_url)
            except Exception as exc:
                return f"Failed to configure remote:\n{exc}"

    # A repo with no commits (fresh init, or clone of an empty remote) has an
    # unborn HEAD; give it a root commit so the push pipeline can stash,
    # branch, and return to this branch reliably.
    head_check = git_fn(local_path, "rev-parse", "--verify", "-q", "HEAD", check=False)
    if head_check.returncode != 0:
        try:
            git_fn(local_path, "commit", "--allow-empty", "-m", "Initialize repository")
            if logger:
                logger.info("Created initial empty commit in %s", local_path)
        except Exception as exc:
            return (
                "Failed to create the repository's initial commit. Make sure git "
                f"user.name and user.email are configured.\n{exc}"
            )

    return None


__all__ = [
    "convert_github_url",
    "default_path_for_new_repo",
    "derive_repo_name_from_url",
    "ensure_export_subfolder_exists",
    "expand_export_subfolder",
    "normalize_export_subfolder",
    "setup_new_repository",
    "validate_repo_inputs",
]
