"""Offline CLI harness for testing the FusionToGitHub Git pipeline without Fusion."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Import core functions - handle both standalone and installed scenarios
try:
    from fusion_git_core import (
        VERSION,
        MODE_SINGLE,
        MODE_SNAPSHOT,
        GitUI,
        git_available,
        push_export,
    )
except ImportError:
    # Add current directory to path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    from fusion_git_core import (
        VERSION,
        MODE_SINGLE,
        MODE_SNAPSHOT,
        GitUI,
        git_available,
        push_export,
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


def _repo_relative(repo: Path, file_path: str) -> str:
    """Where a file goes in the repository: its path inside the repo, else its name."""
    try:
        return Path(file_path).resolve().relative_to(repo).as_posix()
    except ValueError:
        return Path(file_path).name


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the FusionToGitHub git pipeline outside Fusion for smoke testing " "and CI automation.")
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"FusionToGitHub {VERSION}",
        help="Print the version and exit",
    )
    parser.add_argument("--repo", required=True, help="Path to the existing Git repository")
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help=(
            "Files to commit. A file inside the repository keeps its path there; "
            "a file elsewhere is committed at the repository root under its own name."
        ),
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
    parser.add_argument(
        "--mode",
        choices=[MODE_SNAPSHOT, MODE_SINGLE],
        default=MODE_SNAPSHOT,
        help="snapshot: a new branch per export (default); single: one running history on one branch",
    )
    parser.add_argument(
        "--target-branch",
        help="Branch for --mode single (default: the repository's default branch on GitHub)",
    )
    parser.add_argument("--branch-override", help="Explicit branch name to use instead of template")
    parser.add_argument("--design-name", default="OfflineDesign", help="Name used for placeholder tokens")
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
    missing = [p for p in files_to_add if not os.path.isfile(p)]
    if missing:
        sys.stderr.write("These files do not exist:\n")
        for entry in missing:
            sys.stderr.write(f"  - {entry}\n")
        return 2
    if not files_to_add:
        sys.stderr.write("Nothing to push: pass the exported files with --files.\n")
        return 2

    ui = TerminalUI(assume_yes=args.assume_yes)
    pat_credentials = None
    if args.pat_token:
        pat_credentials = {"username": args.pat_username or "", "token": args.pat_token}

    exports = [(path, _repo_relative(repo_path, path)) for path in files_to_add]
    logger.info("FusionToGitHub CLI harness %s", VERSION)
    result = push_export(
        str(repo_path),
        exports,
        args.commit_template,
        args.design_name,
        ui,
        mode=args.mode,
        branch_format_str=args.branch_template,
        branch_override=args.branch_override,
        target_branch=args.target_branch,
        pat_credentials=pat_credentials,
        logger=logger,
    )

    if result is None:
        logger.error("Git pipeline failed. See output above for details.")
        return 1
    if result.get("cancelled"):
        sys.stdout.write("Push cancelled by user; nothing was pushed.\n")
        return 3

    summary = [
        "Push completed via CLI harness:",
        f"  • Branch: {result.get('branch')}",
        f"  • Commit: {result.get('commit')}",
        "  • Files: " + ", ".join(result.get("files") or []),
    ]
    if result.get("reused_branch"):
        summary.append("  • Added a new commit to the existing branch")
    if result.get("bootstrapped"):
        summary.append("  • The repository was empty; added a first commit to main")
    sys.stdout.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
