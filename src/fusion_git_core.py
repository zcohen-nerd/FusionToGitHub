"""Core Git operations shared by the Fusion add-in and offline CLI harness."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, Sequence

VERSION = "V7.7"
IS_WINDOWS = os.name == "nt"
GIT_EXE = shutil.which("git") or (r"C:\\Program Files\\Git\\bin\\git.exe" if IS_WINDOWS else "git")


class GitUI(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def confirm(self, message: str) -> bool: ...


def sanitize_branch_name(raw: Optional[str]) -> str:
    candidate = (raw or "").strip()
    candidate = re.sub(r"[^\w\-\./_]+", "_", candidate)
    candidate = candidate.strip(" .")
    candidate = candidate.lstrip("/")
    candidate = candidate.rstrip("/")
    if not candidate:
        candidate = "fusion-export"
    if len(candidate) > 200:
        candidate = candidate[:200]
    return candidate


def generate_branch_name(template: str, design_basename: str, timestamp: Optional[str] = None):
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_template = template or "fusion-export/{filename}-{timestamp}"
    populated = branch_template.replace("{filename}", design_basename).replace("{timestamp}", ts)
    return sanitize_branch_name(populated), ts


def git_run(repo_path: str, *args: str, check: bool = True, env: Optional[Dict[str, str]] = None):
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    proc = subprocess.run(
        [GIT_EXE, *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        creationflags=creation_flags,
        env=env_vars,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stderr or proc.stdout}")
    return proc


def git_output(repo_path: str, *args: str, env: Optional[Dict[str, str]] = None) -> str:
    return (git_run(repo_path, *args, check=True, env=env).stdout or "").strip()


def git_available() -> bool:
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
        subprocess.run(
            [GIT_EXE, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            creationflags=creation_flags,
        )
        return True
    except Exception:
        return False


@contextmanager
def git_askpass_env(username: str, token: str):
    if not token:
        yield {}
        return

    temp_dir = tempfile.mkdtemp(prefix="fusion_git_auth_")
    script_path = os.path.join(
        temp_dir,
        "askpass.bat" if IS_WINDOWS else "askpass.sh",
    )

    escaped_username = (username or "").replace("%", "%%")
    escaped_token = (token or "").replace("%", "%%")
    username_sh = (username or "").replace("'", "'\"'\"'")
    token_sh = (token or "").replace("'", "'\"'\"'")

    if IS_WINDOWS:
        script_contents = (
            "@echo off\n"
            "set PROMPT=%*\n"
            'echo %PROMPT% | findstr /I "Username" >nul\n'
            f"if %errorlevel%==0 (\n    echo {escaped_username}\n) else (\n    echo {escaped_token}\n)\n"
        )
    else:
        script_contents = (
            "#!/bin/sh\n"
            'prompt="$1"\n'
            'case "$prompt" in\n'
            f"  *Username* ) printf '%s\\n' '{username_sh}' ;;\n"
            f"  *username* ) printf '%s\\n' '{username_sh}' ;;\n"
            f"  *Password* ) printf '%s\\n' '{token_sh}' ;;\n"
            f"  *password* ) printf '%s\\n' '{token_sh}' ;;\n"
            f"  * ) printf '%s\\n' '{token_sh}' ;;\n"
            "esac\n"
        )

    with open(script_path, "w", encoding="utf-8") as askpass_file:
        askpass_file.write(script_contents)
    if not IS_WINDOWS:
        os.chmod(script_path, 0o700)

    env_map = {
        "GIT_ASKPASS": script_path,
        "GIT_TERMINAL_PROMPT": "0",
    }

    try:
        yield env_map
    finally:
        try:
            os.remove(script_path)
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def handle_git_operations(
    repo_path: str,
    file_abs_paths_to_add: Sequence[str],
    commit_msg_template: str,
    branch_format_str: str,
    ui: GitUI,
    design_basename_for_branch: str,
    *,
    branch_override: Optional[str] = None,
    skip_pull: bool = False,
    pat_credentials: Optional[Dict[str, str]] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    our_stash_msg = "fusion_git_addin_autostash"
    original_branch: Optional[str] = None
    stashed = False
    used_force_push = bool(skip_pull)
    branch_name_final: Optional[str] = None
    timestamp_str: Optional[str] = None
    pull_failure_details: Optional[str] = None

    def _perform(git_env: Optional[Dict[str, str]]):
        nonlocal original_branch, stashed, used_force_push, branch_name_final, timestamp_str, pull_failure_details, skip_pull  # noqa: E501

        remotes = git_output(repo_path, "remote", env=git_env).splitlines()
        if "origin" not in remotes:
            ui.error("No 'origin' remote found in this repo.")
            if logger:
                logger.error("No 'origin' remote in %s", repo_path)
            return {"cancelled": True}

        head = git_output(repo_path, "rev-parse", "--abbrev-ref", "HEAD", env=git_env)
        detached = head.strip() == "HEAD"
        if not detached:
            original_branch = head.strip()

        if detached:
            try:
                ref = git_output(
                    repo_path,
                    "symbolic-ref",
                    "refs/remotes/origin/HEAD",
                    "--short",
                    env=git_env,
                )
                default_branch = ref.split("/")[-1]
            except Exception:
                branches = {
                    b.strip().lstrip("* ").strip() for b in git_output(repo_path, "branch", env=git_env).splitlines()
                }
                if "main" in branches:
                    default_branch = "main"
                elif "master" in branches:
                    default_branch = "master"
                else:
                    default_branch = None
            if not default_branch:
                ui.error("Unable to determine default branch while in detached HEAD.")
                if logger:
                    logger.error("Cannot determine default branch")
                return {"cancelled": True}
            git_run(repo_path, "checkout", default_branch, env=git_env)
            original_branch = default_branch
            if logger:
                logger.info("Detached HEAD → switched to '%s'", default_branch)

        status = git_output(repo_path, "status", "--porcelain", env=git_env)
        if status.strip():
            if not ui.confirm(
                "Local changes detected. We'll stash them temporarily before pushing.\n"
                "Continue and auto-stash these changes?"
            ):
                if logger:
                    logger.info("User cancelled due to dirty working tree.")
                return {"cancelled": True}
            git_run(repo_path, "stash", "push", "-u", "-m", our_stash_msg, env=git_env)
            stashed = True
            if logger:
                logger.info("Stashed local changes.")

        if not skip_pull:
            try:
                git_run(repo_path, "pull", "--rebase", "origin", original_branch, env=git_env)
            except Exception as pull_exc:
                pull_failure_details = str(pull_exc)
                if ui.confirm(
                    "git pull --rebase failed.\n\n"
                    f"Details:\n{pull_failure_details}\n\n"
                    "Would you like to skip pulling and force-push this export instead?"
                ):
                    skip_pull = True
                    used_force_push = True
                    if logger:
                        logger.warning("Pull failed; proceeding with force push.")
                else:
                    raise

        if skip_pull:
            used_force_push = True

        default_branch_name, timestamp_str = generate_branch_name(
            branch_format_str,
            design_basename_for_branch,
        )
        branch_name_final = default_branch_name
        if branch_override:
            override_clean = sanitize_branch_name(branch_override)
            if not override_clean:
                ui.error("Provided branch name is invalid after sanitization.")
                raise RuntimeError("Invalid branch name override.")
            branch_name_final = override_clean

        git_run(repo_path, "checkout", "-b", branch_name_final, env=git_env)

        changelog_file_path = os.path.join(repo_path, "CHANGELOG.md")
        log_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = commit_msg_template or "Design update: {filename}"
        commit_msg = (
            commit_msg.replace("{filename}", design_basename_for_branch)
            .replace("{branch}", branch_name_final)
            .replace("{timestamp}", timestamp_str)
        )

        entry_lines = [
            f"## {log_timestamp} - {design_basename_for_branch}",
            f"- **Branch:** `{branch_name_final}`",
            f'- **Commit Message:** "{commit_msg}"',
        ]
        if file_abs_paths_to_add:
            entry_lines.append("- **Files Updated:**")
            for f in file_abs_paths_to_add:
                try:
                    rel_display = os.path.relpath(f, repo_path)
                except Exception:
                    rel_display = os.path.basename(f)
                entry_lines.append(f"  - `{rel_display}`")
        entry_lines.append("\n---\n")

        changelog_header = "# Changelog\n\n"
        existing = ""
        if os.path.exists(changelog_file_path):
            with open(changelog_file_path, "r", encoding="utf-8") as fr:
                existing = fr.read()
            if existing.startswith(changelog_header):
                existing = existing[len(changelog_header) :]
        with open(changelog_file_path, "w", encoding="utf-8") as fw:
            fw.write(changelog_header)
            fw.write("\n".join(entry_lines) + "\n")
            fw.write(existing)

        files_abs = [os.path.join(repo_path, "CHANGELOG.md")] + [
            os.path.normpath(p) for p in (file_abs_paths_to_add or [])
        ]
        missing = [p for p in files_abs if not os.path.exists(p)]
        if missing:
            try:
                listing = "\n".join(sorted(os.listdir(repo_path)))
            except Exception:
                listing = "(dir list failed)"
            msg = (
                "Exported files not found in repo folder:\n" + "\n".join(missing) + f"\n\nRepo root listing:\n{listing}"
            )
            ui.error(msg)
            if logger:
                logger.error(msg)
            return {"cancelled": True}

        rels = ["CHANGELOG.md"]
        for p in file_abs_paths_to_add or []:
            rels.append(os.path.relpath(os.path.normpath(p), repo_path))

        git_run(repo_path, "add", *rels, env=git_env)
        git_run(repo_path, "commit", "-m", commit_msg, env=git_env)

        push_args = ["push"]
        if skip_pull:
            push_args.append("--force-with-lease")
        push_args.extend(["-u", "origin", branch_name_final])
        git_run(repo_path, *push_args, env=git_env)

        return {
            "branch": branch_name_final,
            "stashed": stashed,
            "force_push": used_force_push,
            "timestamp": timestamp_str,
            "pull_failed": pull_failure_details,
        }

    try:
        if pat_credentials and pat_credentials.get("token"):
            username = pat_credentials.get("username", "")
            with git_askpass_env(username, pat_credentials.get("token", "")) as env_map:
                result = _perform(env_map)
        else:
            result = _perform(None)
        if result and result.get("cancelled"):
            return None
        return result
    except Exception as exc:
        msg = f"Git operation failed:\n{exc}"
        ui.error(msg)
        if logger:
            logger.error(msg, exc_info=True)
        return None
    finally:
        try:
            if original_branch:
                git_run(repo_path, "checkout", original_branch, check=False)
        except Exception:
            if logger:
                logger.warning("Failed to restore branch '%s'", original_branch, exc_info=True)
        if stashed:
            try:
                git_run(repo_path, "stash", "pop", "stash@{0}", check=False)
            except Exception:
                if logger:
                    logger.warning("Auto-stash pop failed; original changes remain stashed.", exc_info=True)


__all__ = [
    "VERSION",
    "IS_WINDOWS",
    "GIT_EXE",
    "GitUI",
    "sanitize_branch_name",
    "generate_branch_name",
    "git_run",
    "git_output",
    "git_available",
    "git_askpass_env",
    "handle_git_operations",
]
