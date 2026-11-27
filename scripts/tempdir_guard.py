#!/usr/bin/env python3
"""Fail if the test suites leave temporary folders behind.

    python scripts/tempdir_guard.py snapshot STATE_FILE
    ... run the tests ...
    python scripts/tempdir_guard.py check STATE_FILE

Only entries whose names start with the prefixes the add-in and its tests use
are considered, so other programs' temp files don't matter.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

PREFIXES = ("fusion_", "ftg_")


def entries() -> list:
    root = tempfile.gettempdir()
    return sorted(name for name in os.listdir(root) if name.startswith(PREFIXES))


def main(argv: list) -> int:
    if len(argv) != 3 or argv[1] not in ("snapshot", "check"):
        print(__doc__, file=sys.stderr)
        return 2
    state = argv[2]
    if argv[1] == "snapshot":
        with open(state, "w", encoding="utf-8") as fh:
            json.dump(entries(), fh)
        print(f"{len(entries())} pre-existing temp entries recorded in {tempfile.gettempdir()}")
        return 0
    with open(state, encoding="utf-8") as fh:
        before = set(json.load(fh))
    leaked = [name for name in entries() if name not in before]
    if leaked:
        print(f"Tests left {len(leaked)} temporary entries in {tempfile.gettempdir()}:", file=sys.stderr)
        for name in leaked:
            print(f"  {name}", file=sys.stderr)
        return 1
    print("No temporary folders left behind.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
