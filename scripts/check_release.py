#!/usr/bin/env python3
"""Check that every version surface agrees before a release.

    python scripts/check_release.py                      # consistency only
    python scripts/check_release.py --tag 0.3.3          # also: tag matches, changelog dated
    python scripts/check_release.py --tag 0.3.3 --require-on-main

The manifest version is the single source of truth (maintainer decision Q4).
Everything else must match it:

- ``VERSION`` in ``src/fusion_git_core.py``
- the top ``## <version>`` heading of ``CHANGELOG.md``
- the README's stated version
- the release tag, exactly (numeric, no ``v`` prefix), when ``--tag`` is given

It also checks the frozen add-in ID, and with ``--require-on-main`` that the
tagged commit is on ``origin/main`` (releases are only cut from main).

Exits 0 when everything passes, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from package import ADDIN_ID, VERSION_RE  # noqa: E402


def manifest_version(root: Path = ROOT) -> str:
    manifest = json.loads((root / "src" / "Push_To_GitHub.manifest").read_text(encoding="utf-8"))
    return str(manifest.get("version", ""))


def check(root: Path = ROOT, tag: Optional[str] = None, require_on_main: bool = False) -> List[str]:
    """Return a list of problems; empty means the release surfaces agree."""
    problems: List[str] = []
    manifest = json.loads((root / "src" / "Push_To_GitHub.manifest").read_text(encoding="utf-8"))
    version = str(manifest.get("version", ""))
    if not VERSION_RE.match(version):
        problems.append(f"manifest version {version!r} is not X.Y.Z")

    if str(manifest.get("id", "")).lower() != ADDIN_ID:
        problems.append(f"manifest id {manifest.get('id')!r} is not the frozen add-in ID {ADDIN_ID}")

    core = (root / "src" / "fusion_git_core.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([^"]+)"', core, re.MULTILINE)
    if not match:
        problems.append("VERSION not found in src/fusion_git_core.py")
    elif match.group(1) != version:
        problems.append(f"fusion_git_core.VERSION {match.group(1)!r} != manifest {version!r}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## (.+)$", changelog, re.MULTILINE)
    heading_text = heading.group(1).strip() if heading else ""
    heading_version = heading_text.split()[0] if heading_text else ""
    if heading_version != version:
        problems.append(f"top CHANGELOG heading {heading_text!r} is not for {version}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if f"`{version}`" not in readme:
        problems.append(f"README does not state the version `{version}`")

    if tag is not None:
        if tag != version:
            problems.append(
                f"tag {tag!r} does not match manifest version {version!r} "
                "(tags are the bare version, e.g. 0.3.3)"
            )
        if "unreleased" in heading_text.lower():
            problems.append(
                f"CHANGELOG heading {heading_text!r} still says Unreleased; "
                "set the release date before tagging"
            )

    if require_on_main:
        target = f"refs/tags/{tag}" if tag else "HEAD"
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", f"{target}^{{commit}}", "origin/main"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 1:
            problems.append(f"{target} is not on origin/main; release only from merged commits")
        elif proc.returncode != 0:
            problems.append(f"could not check {target} against origin/main: {proc.stderr.strip()}")

    return problems


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check release version consistency.")
    parser.add_argument("--tag", help="release tag to check (the bare version, e.g. 0.3.3)")
    parser.add_argument(
        "--require-on-main",
        action="store_true",
        help="fail unless the tag (or HEAD) is reachable from origin/main",
    )
    args = parser.parse_args(argv)
    problems = check(tag=args.tag, require_on_main=args.require_on_main)
    if problems:
        print("Release check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"Release check passed for {manifest_version()}" + (f" (tag {args.tag})" if args.tag else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
