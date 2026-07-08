"""Offline CLI harness for testing the FusionToGitHub Git pipeline without Fusion."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Import core functions - handle both standalone and installed scenarios
try:
    from fusion_git_core import (
        VERSION,
        GitUI,
        git_available,
        handle_git_operations,
    )
except ImportError:
    # Add current directory to path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    from fusion_git_core import (
        VERSION,
        GitUI,
        git_available,
        handle_git_operations,
    )


class TerminalUI(GitUI):
    def __init__(self, *, assume_yes: bool = False):
        self._assume_yes = assume_yes

    def _write(self, prefix: str, message: str) -> None:
        sys.stdout.write(f"[{prefix}] {message}\n")
        sys.stdout.flush()

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def confirm(self, message: str) -> bool:
        if self._assume_yes:
            self._write("CONFIRM", f"{message} -> yes (assumed)")
            return True
        prompt = f"{message} [y/N]: "
        try:
            response = input(prompt)
        except EOFError:
            return False
        accepted = response.strip().lower() in {"y", "yes"}
        self._write("CONFIRM", f"{message} -> {'yes' if accepted else 'no'}")
        return accepted


def _abs_paths(repo: Path, entries: list[str]) -> list[str]:
    resolved: list[str] = []
    for entry in entries:
        path = Path(entry)
        if not path.is_absolute():
            path = repo / path
        resolved.append(str(path.resolve()))
    return resolved


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the FusionToGitHub git pipeline outside Fusion for smoke testing " "and CI automation.")
    )
    parser.add_argument("--repo", required=True, help="Path to the existing Git repository")
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Absolute or repo-relative paths to include in the commit (optional)",
    )
    parser.add_argument(
        "--commit-template",
        default="Design update: {filename}",
        help="Commit message template; supports {filename}, {branch}, {timestamp}",
    )
    parser.add_argument(
        "--branch-template",
        default="fusion-export/{filename}-{timestamp}",
        help="Branch name template; supports {filename} and {timestamp}",
    )
    parser.add_argument("--branch-override", help="Explicit branch name to use instead of template")
    parser.add_argument("--design-name", default="OfflineDesign", help="Name used for placeholder tokens")
    parser.add_argument("--skip-pull", action="store_true", help="Skip git pull --rebase and force push")
    parser.add_argument("--assume-yes", action="store_true", help="Auto-accept confirmation prompts")
    parser.add_argument("--pat-token", help="Personal access token to feed via askpass")
    parser.add_argument("--pat-username", default="", help="Username to pair with the PAT (if required)")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity for the CLI harness",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    logger = logging.getLogger("FusionToGitHub.CLI")

    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.exists():
        sys.stderr.write(f"Repository path not found: {repo_path}\n")
        return 2
    if not (repo_path / ".git").exists():
        sys.stderr.write(f"No .git directory detected at {repo_path}\n")
        return 2

    if not git_available():
        sys.stderr.write("Git executable not found on PATH. Install Git before using the harness.\n")
        return 2

    files_to_add = _abs_paths(repo_path, args.files)
    if not files_to_add:
        logger.info("No file list provided; only CHANGELOG.md will be committed if changed.")
    else:
        missing = [p for p in files_to_add if not os.path.exists(p)]
        if missing:
            sys.stderr.write("The following files do not exist and will be skipped:\n")
            for entry in missing:
                sys.stderr.write(f"  - {entry}\n")
            files_to_add = [p for p in files_to_add if os.path.exists(p)]

    ui = TerminalUI(assume_yes=args.assume_yes)
    pat_credentials = None
    if args.pat_token:
        pat_credentials = {"username": args.pat_username or "", "token": args.pat_token}

    # Snapshot the files now and let the pipeline re-materialize them after
    # the export branch is created. Otherwise the pipeline's auto-stash would
    # sweep away untracked/modified files before they can be committed.
    snapshot_dir = None
    materialize = None
    if files_to_add:
        snapshot_dir = tempfile.mkdtemp(prefix="fusion_cli_snapshot_")
        snapshot_map = {}
        for index, dest_path in enumerate(files_to_add):
            snap_path = os.path.join(snapshot_dir, f"{index}_{os.path.basename(dest_path)}")
            shutil.copy2(dest_path, snap_path)
            snapshot_map[dest_path] = snap_path

        def materialize() -> list[str]:
            for dest_path, snap_path in snapshot_map.items():
                dest_dir = os.path.dirname(dest_path)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(snap_path, dest_path)
            return list(snapshot_map)

    logger.info("FusionToGitHub CLI harness %s", VERSION)
    try:
        result = handle_git_operations(
            str(repo_path),
            [],
            args.commit_template,
            args.branch_template,
            ui,
            args.design_name,
            branch_override=args.branch_override,
            skip_pull=args.skip_pull,
            pat_credentials=pat_credentials,
            logger=logger,
            materialize_files=materialize,
        )
    finally:
        if snapshot_dir:
            shutil.rmtree(snapshot_dir, ignore_errors=True)

    if not result:
        logger.error("Git pipeline aborted or failed. See output above for details.")
        return 1

    summary = [
        "Push completed via CLI harness:",
        f"  • Branch: {result.get('branch')}",
    ]
    if result.get("reused_branch"):
        summary.append("  • Added a new commit to the existing branch")
    if result.get("force_push"):
        summary.append("  • Force push was used (--force-with-lease)")
    if result.get("stashed"):
        summary.append("  • Local changes were auto-stashed and restored")
    if result.get("pull_failed"):
        summary.append("  • Pull failed before force push; inspect logs")
    sys.stdout.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
