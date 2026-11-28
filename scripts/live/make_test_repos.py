#!/usr/bin/env python3
"""Create (and later delete) disposable private GitHub repositories for the live campaign.

    python scripts/live/make_test_repos.py create            # ftg-live-<date>-a, -b, -protected
    python scripts/live/make_test_repos.py create --no-protected
    python scripts/live/make_test_repos.py list
    python scripts/live/make_test_repos.py delete            # asks before each one

Uses the GitHub CLI (`gh`), signed in as you. Every repository it creates is
**private** and named `ftg-live-…`; it never lists, changes or deletes any
other repository. `-protected` starts with a README on `main` and gets branch
protection (pull requests required) for live check U16. Deleting needs the
`delete_repo` scope: `gh auth refresh -s delete_repo`.

This script talks to GitHub with your account: read it before running it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from typing import List

PREFIX = "ftg-live-"


def gh(*args: str, input_text: str = "") -> str:
    proc = subprocess.run(["gh", *args], input=input_text or None, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def owner() -> str:
    return gh("api", "user", "--jq", ".login")


def ours() -> List[str]:
    listing = json.loads(gh("repo", "list", owner(), "--limit", "200", "--json", "name,visibility"))
    return sorted(r["name"] for r in listing if r["name"].startswith(PREFIX))


def create(protected: bool) -> None:
    login = owner()
    stamp = datetime.date.today().strftime("%Y%m%d")
    names = [f"{PREFIX}{stamp}-a", f"{PREFIX}{stamp}-b"]
    for name in names:
        gh("repo", "create", f"{login}/{name}", "--private",
           "--description", "Disposable: Push to GitHub live test")
        print(f"created https://github.com/{login}/{name}  (empty)")
    if protected:
        name = f"{PREFIX}{stamp}-protected"
        gh("repo", "create", f"{login}/{name}", "--private", "--add-readme",
           "--description", "Disposable: Push to GitHub live test (protected main)")
        rules = {
            "required_status_checks": None,
            "enforce_admins": True,
            "required_pull_request_reviews": {"required_approving_review_count": 0},
            "restrictions": None,
        }
        gh("api", "-X", "PUT", f"repos/{login}/{name}/branches/main/protection", "--input", "-",
           input_text=json.dumps(rules))
        print(f"created https://github.com/{login}/{name}  (main protected, for U16)")


def delete() -> None:
    login = owner()
    for name in ours():
        typed = input(f"Delete {login}/{name}? Type its name to confirm (Enter skips): ").strip()
        if typed == name:
            gh("repo", "delete", f"{login}/{name}", "--yes")
            print(f"deleted {name}")
        else:
            print(f"kept {name}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("create", "list", "delete"))
    parser.add_argument("--no-protected", action="store_true", help="skip the protected-branch repository")
    args = parser.parse_args(argv)
    if args.command == "create":
        create(not args.no_protected)
    elif args.command == "list":
        print("\n".join(ours()) or "(none)")
    else:
        delete()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
