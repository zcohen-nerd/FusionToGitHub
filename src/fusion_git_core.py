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
from typing import Any, Callable, Dict, Optional, Protocol, Sequence

VERSION = "V7.7"
IS_WINDOWS = os.name == "nt"
GIT_EXE = shutil.which("git") or (r"C:\Program Files\Git\bin\git.exe" if IS_WINDOWS else "git")


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
        # Delayed expansion (!VAR!) keeps special characters in the values
        # from being re-parsed by cmd; 'if defined' avoids the literal
        # '!VAR!' output cmd produces for undefined delayed variables.
        script_contents = (
            "@echo off\n"
            "setlocal EnableDelayedExpansion\n"
            'echo %* | findstr /I "Username" >nul\n'
            "if %errorlevel%==0 (\n"
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
        script_contents = (
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *[Uu]sername* ) printf '%s\\n' \"$FUSION_GIT_ASKPASS_USERNAME\" ;;\n"
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
    materialize_files: Optional[Callable[[], Sequence[str]]] = None,
) -> Optional[Dict[str, Any]]:
    """Run the stash → pull → branch → commit → push pipeline.

    When *materialize_files* is given, it is invoked after the export branch
    has been created and must place the files into the working tree, returning
    their absolute paths (which replace *file_abs_paths_to_add*). Keeping the
    exports out of the tree until after the stash/pull steps guarantees they
    are committed exactly as exported and never swallowed by the auto-stash.
    """
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

        head_proc = git_run(repo_path, "symbolic-ref", "--short", "-q", "HEAD", check=False, env=git_env)
        detached = head_proc.returncode != 0
        if not detached:
            original_branch = (head_proc.stdout or "").strip()

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

        # A repository with no commits yet (fresh init/clone of an empty
        # remote) has an unborn HEAD: nothing is tracked, so there is
        # nothing to stash, and several git commands behave differently.
        unborn = (
            git_run(repo_path, "rev-parse", "--verify", "-q", "HEAD", check=False, env=git_env).returncode != 0
        )

        if unborn:
            if logger:
                logger.info("Repository has no commits yet; skipping the auto-stash step.")
        else:
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
                # A conflicted rebase must never leak out of the pipeline:
                # abort it so the repository is back in its pre-pull state
                # before we decide what to do next.
                git_run(repo_path, "rebase", "--abort", check=False, env=git_env)
                details = str(pull_exc)
                if "couldn't find remote ref" in details:
                    # Brand-new/empty remote: there is simply nothing to
                    # pull yet, so continue with a regular (non-force) push.
                    if logger:
                        logger.info(
                            "Remote 'origin' has no branch '%s' yet; skipping pull.",
                            original_branch,
                        )
                elif ui.confirm(
                    "git pull --rebase failed.\n\n"
                    f"Details:\n{details}\n\n"
                    "Would you like to skip pulling and force-push this export instead?"
                ):
                    pull_failure_details = details
                    skip_pull = True
                    used_force_push = True
                    if logger:
                        logger.warning("Pull failed; proceeding with force push.")
                else:
                    pull_failure_details = details
                    raise

        if skip_pull:
            used_force_push = True

        default_branch_name, timestamp_str = generate_branch_name(
            branch_format_str,
            design_basename_for_branch,
        )
        branch_name_final = default_branch_name
        reused_branch = False

        def _local_branch_exists(name: str) -> bool:
            return (
                git_run(
                    repo_path, "rev-parse", "--verify", "-q", f"refs/heads/{name}", check=False, env=git_env
                ).returncode
                == 0
            )

        if branch_override:
            override_clean = sanitize_branch_name(branch_override)
            if not override_clean:
                ui.error("Provided branch name is invalid after sanitization.")
                raise RuntimeError("Invalid branch name override.")
            branch_name_final = override_clean
            if _local_branch_exists(branch_name_final):
                # The user named this branch explicitly; reusing it (appending
                # a new commit) is the likely intent, but confirm first.
                if not ui.confirm(
                    f"Branch '{branch_name_final}' already exists.\n\n"
                    "Add this export as a new commit on the existing branch?"
                ):
                    if logger:
                        logger.info("User declined to reuse existing branch '%s'.", branch_name_final)
                    return {"cancelled": True}
                reused_branch = True
        else:
            # Template-generated names can collide (e.g. two exports within
            # the same second); pick a unique name instead of failing.
            candidate = branch_name_final
            suffix = 2
            while _local_branch_exists(candidate):
                candidate = f"{branch_name_final}-{suffix}"
                suffix += 1
            if candidate != branch_name_final and logger:
                logger.info("Branch '%s' already exists; using '%s' instead.", branch_name_final, candidate)
            branch_name_final = candidate

        if reused_branch:
            git_run(repo_path, "checkout", branch_name_final, env=git_env)
        else:
            git_run(repo_path, "checkout", "-b", branch_name_final, env=git_env)

        # Only now — with the stash/pull steps done and the export branch
        # checked out — do the export files enter the working tree.
        files_to_commit = [os.path.normpath(p) for p in (file_abs_paths_to_add or [])]
        if materialize_files is not None:
            files_to_commit = [os.path.normpath(p) for p in (materialize_files() or [])]

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
        if files_to_commit:
            entry_lines.append("- **Files Updated:**")
            for f in files_to_commit:
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

        files_abs = [os.path.join(repo_path, "CHANGELOG.md")] + files_to_commit
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
        for p in files_to_commit:
            rels.append(os.path.relpath(p, repo_path))

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
            "reused_branch": reused_branch,
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
        restore_ok = False
        try:
            if original_branch:
                branch_exists = (
                    git_run(
                        repo_path, "rev-parse", "--verify", "-q", f"refs/heads/{original_branch}", check=False
                    ).returncode
                    == 0
                )
                if branch_exists:
                    restore_proc = git_run(repo_path, "checkout", original_branch, check=False)
                    restore_ok = restore_proc.returncode == 0
                    if not restore_ok:
                        msg = (
                            f"Could not switch back to branch '{original_branch}'.\n"
                            f"The repository is still on '{branch_name_final or 'the export branch'}'.\n"
                            f"Details:\n{restore_proc.stderr or restore_proc.stdout}"
                        )
                        ui.warn(msg)
                        if logger:
                            logger.warning(msg)
                elif logger:
                    # Original branch had no commits (brand-new repository):
                    # there is no ref to return to, so stay on the export branch.
                    logger.info(
                        "Original branch '%s' has no commits; staying on '%s'.",
                        original_branch,
                        branch_name_final,
                    )
        except Exception:
            if logger:
                logger.warning("Failed to restore branch '%s'", original_branch, exc_info=True)
        if stashed:
            try:
                stash_ref = None
                stash_list = git_run(repo_path, "stash", "list", check=False)
                for line in (stash_list.stdout or "").splitlines():
                    if our_stash_msg in line:
                        stash_ref = line.split(":", 1)[0].strip()
                        break
                if stash_ref is None:
                    if logger:
                        logger.warning("Auto-stash entry not found; nothing to restore.")
                elif not restore_ok:
                    msg = (
                        f"Your local changes were auto-stashed but could not be restored because the "
                        f"original branch was not restored. They remain stashed as '{stash_ref}' "
                        f"({our_stash_msg}). Run 'git stash pop {stash_ref}' once the repository is back "
                        f"on '{original_branch}'."
                    )
                    ui.warn(msg)
                    if logger:
                        logger.warning(msg)
                else:
                    pop_proc = git_run(repo_path, "stash", "pop", stash_ref, check=False)
                    if pop_proc.returncode != 0:
                        msg = (
                            f"Your auto-stashed local changes could not be restored automatically and "
                            f"remain stashed as '{stash_ref}' ({our_stash_msg}).\n"
                            f"Run 'git stash pop {stash_ref}' to recover them.\n"
                            f"Details:\n{pop_proc.stderr or pop_proc.stdout}"
                        )
                        ui.warn(msg)
                        if logger:
                            logger.warning(msg)
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
