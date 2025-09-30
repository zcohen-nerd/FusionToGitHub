"""Offline CLI harness for testing the FusionToGitHub Git pipeline without Fusion."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

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

    logger.info("FusionToGitHub CLI harness %s", VERSION)
    result = handle_git_operations(
        str(repo_path),
        files_to_add,
        args.commit_template,
        args.branch_template,
        ui,
        args.design_name,
        branch_override=args.branch_override,
        skip_pull=args.skip_pull,
        pat_credentials=pat_credentials,
        logger=logger,
    )

    if not result:
        logger.error("Git pipeline aborted or failed. See output above for details.")
        return 1

    summary = [
        "Push completed via CLI harness:",
        f"  • Branch: {result.get('branch')}",
    ]
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
