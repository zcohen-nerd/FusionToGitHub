"""Pure helper functions extracted from the Fusion dialog handler.

These functions have no Fusion 360 API dependencies and can be tested
independently outside the add-in runtime.
"""

from __future__ import annotations

import os
import re
from typing import Optional


def convert_github_url(url: str) -> str:
    """Convert any GitHub URL format to the proper Git clone URL.

    Handles browser URLs, trailing slashes, query params, and fragment
    identifiers.  Returns the URL unchanged if it already ends with
    ``.git`` or uses a recognised scheme.
    """
    if not url.strip():
        return url

    url = url.strip()

    # Already a proper Git URL – keep as-is
    if url.endswith(".git"):
        return url

    # Convert GitHub web URLs to Git clone URLs
    # Pattern: https://github.com/user/repo or https://github.com/user/repo/
    web_pattern = r"https://github\.com/([^/]+)/([^/]+)/?(?:\?.*)?(?:#.*)?$"
    match = re.match(web_pattern, url)
    if match:
        user, repo = match.groups()
        return f"https://github.com/{user}/{repo}.git"

    # If it's already a valid Git URL format, keep it
    if re.match(r"^(https://|git@|ssh://).+", url):
        return url

    # If none of the above, assume it needs .git added
    if not url.endswith(".git"):
        return url + ".git"

    return url


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
    """Initialise a local Git repo and configure ``origin``.

    *git_fn* must be a callable with the same signature as
    ``_git(repo_path, *args, check=…)``.

    Returns ``None`` on success or an error message string on failure.
    """
    if not os.path.exists(local_path):
        os.makedirs(local_path, exist_ok=True)

    git_dir_path = os.path.join(local_path, ".git")
    needs_init = not os.path.isdir(git_dir_path)

    if needs_init:
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

    return None


__all__ = [
    "convert_github_url",
    "default_path_for_new_repo",
    "setup_new_repository",
    "validate_repo_inputs",
]
