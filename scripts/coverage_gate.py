#!/usr/bin/env python3
"""Enforce per-module coverage, and keep the tests honest.

    python scripts/coverage_gate.py coverage.json

*coverage.json* comes from ``coverage json`` after running both suites with
branch coverage (see the Coverage job in .github/workflows/ci.yml).

Checks:

1. **Every runtime module has a threshold.** A new file in src/ can't skip
   the gate by not being listed; developer tools are listed explicitly as
   exempt, with the reason.
2. **Each module meets its own threshold** (statements + branches, as
   ``coverage`` reports them). Per-module limits stop a well-tested module
   from hiding an untested one in an overall average.
3. **Every unit test asserts something unconditionally.** A test method
   whose only assertions sit inside an ``if`` (which may never run), or that
   has none at all, would raise coverage without checking anything; it fails
   the gate.

Thresholds only go up. Raise one when a module's coverage improves.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Minimum percent_covered (lines + branches) per runtime module.
# Set just below the level measured when the gate was introduced (S3,
# 0.5.0); raise them as tests improve, never lower them.
THRESHOLDS = {
    "fusion_git_core.py": 85,
    "push_controller.py": 90,
    "settings_store.py": 85,
    "portable_names.py": 90,
    "export_checks.py": 90,
    "dialog_helpers.py": 78,
    "push_dialog.py": 77,
    "fusion_export.py": 85,
    "addin_logging.py": 65,
    # 92% in the Windows Coverage job, where the real Credential Manager
    # tests run (FTG_REAL_VAULT_TESTS=1). Locally, without them, it is ~57%:
    # run the gate in CI, or set the variable on a disposable machine.
    "credentials.py": 90,
    # Thin Fusion entry point: mostly import fallbacks and Fusion-only
    # branches. Counted in the add-in layer group below.
    "Push_To_GitHub.py": 50,
    # S4 background push (0.6.0).
    "push_worker.py": 90,
    "fusion_bridge.py": 81,
}
# Combined minimums across related modules (statements + branches).
GROUPS = {
    "add-in layer (Fusion-facing code + push controller)": (
        ("Push_To_GitHub.py", "push_dialog.py", "fusion_export.py", "addin_logging.py", "push_controller.py",
         "fusion_bridge.py"),
        74,
    ),
}
# Not part of the installed add-in (excluded from the package by
# scripts/package.py); exercised by the CLI tests in a subprocess.
EXEMPT = {
    "push_cli.py": "developer tool; tested through subprocess calls (T_PIPE_05, T_CORE_05)",
    "diagnostic.py": "developer tool; not shipped",
}
ASSERTION_NAMES = ("assert", "fail")


def _module_name(path: str) -> str:
    return os.path.basename(path)


def check_thresholds(report: dict) -> list:
    problems = []
    files = {_module_name(path): data for path, data in report["files"].items()}
    for module in sorted(p.name for p in (ROOT / "src").glob("*.py")):
        if module in EXEMPT:
            continue
        if module not in THRESHOLDS:
            problems.append(f"{module}: no coverage threshold set (add it to THRESHOLDS)")
            continue
        data = files.get(module)
        if data is None:
            problems.append(f"{module}: not measured at all (is it imported by any test?)")
            continue
        percent = data["summary"]["percent_covered"]
        if percent + 1e-9 < THRESHOLDS[module]:
            problems.append(f"{module}: {percent:.1f}% < {THRESHOLDS[module]}%")
    for module in THRESHOLDS:
        if not (ROOT / "src" / module).exists():
            problems.append(f"{module}: listed in THRESHOLDS but missing from src/")
    for label, (modules, minimum) in GROUPS.items():
        percent = group_percent(files, modules)
        if percent is None:
            problems.append(f"{label}: not measured")
        elif percent + 1e-9 < minimum:
            problems.append(f"{label}: {percent:.1f}% < {minimum}%")
    return problems


def group_percent(files: dict, modules) -> "float | None":
    covered = total = 0
    for module in modules:
        data = files.get(module)
        if data is None:
            return None
        summary = data["summary"]
        covered += summary["covered_lines"] + summary.get("covered_branches", 0)
        total += summary["num_statements"] + summary.get("num_branches", 0)
    return 100.0 * covered / total if total else None


def _is_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name.startswith(ASSERTION_NAMES)
    return False


def _has_unconditional_assertion(function: ast.FunctionDef) -> bool:
    """True if an assertion runs whenever the test runs (not only inside an ``if``)."""
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.If, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue  # conditional, or only defined here and maybe never called
        if _is_assertion(node):
            return True
        pending.extend(ast.iter_child_nodes(node))
    return False


def check_assertions(test_dir: Path = ROOT / "tests" / "unit") -> list:
    problems = []
    for path in sorted(Path(test_dir).glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test"):
                continue
            if not _has_unconditional_assertion(node):
                problems.append(f"{path.name}::{node.name} has no assertion outside an 'if'")
    return problems


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        report = json.load(fh)
    problems = check_thresholds(report) + check_assertions()
    files = {_module_name(p): d for p, d in report["files"].items()}
    for module in sorted(THRESHOLDS):
        data = files.get(module)
        shown = f"{data['summary']['percent_covered']:.1f}%" if data else "not measured"
        print(f"  {module:22} {shown:>12}   (minimum {THRESHOLDS[module]}%)")
    for label, (modules, minimum) in GROUPS.items():
        percent = group_percent(files, modules)
        shown = f"{percent:.1f}%" if percent is not None else "not measured"
        print(f"  {label}: {shown} (minimum {minimum}%)")
    if problems:
        print("Coverage gate FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("Coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
