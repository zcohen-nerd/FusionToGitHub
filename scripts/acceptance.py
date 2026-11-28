#!/usr/bin/env python3
"""The consolidated live acceptance matrix: check it, render it, summarise it.

    python scripts/acceptance.py check     # validate criteria.csv and steps.csv; fail if renders are stale
    python scripts/acceptance.py render    # write tests/ACCEPTANCE_MATRIX.md and tests/MANUAL_CHECKLIST.md
    python scripts/acceptance.py summary   # counts by status and workflow

``tests/acceptance/criteria.csv`` is the single record of every live
acceptance criterion: what it checks, how, what should happen, and (filled in
during the campaign) what happened, the evidence, the status and any defect.
It opens in a spreadsheet; edit it there or in a text editor, then render.

``tests/acceptance/steps.csv`` orders the criteria into an efficient session
(each step leaves Fusion in the state the next one needs). The renders are
generated: never edit them by hand.

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
CRITERIA = ROOT / "tests" / "acceptance" / "criteria.csv"
STEPS = ROOT / "tests" / "acceptance" / "steps.csv"
MATRIX_MD = ROOT / "tests" / "ACCEPTANCE_MATRIX.md"
CAMPAIGN_MD = ROOT / "tests" / "MANUAL_CHECKLIST.md"

FIELDS = ["id", "workflow", "requirement", "mandatory", "step", "prerequisites", "procedure", "expected",
          "actual", "evidence", "status", "defect"]
STATUSES = ("Not Run", "Pass", "Fail", "Blocked")
MANDATORY = ("yes", "if available")
WORKFLOWS = OrderedDict([
    ("01", "Clean installation and startup"),
    ("02", "Upgrade from the latest public release (0.4.0)"),
    ("03", "Same-process update, rollback and Run on Startup"),
    ("04", "First-time setup and Git authentication"),
    ("05", "Repository and profile management"),
    ("06", "Continuous revision history and snapshot modes"),
    ("07", "CAD export formats"),
    ("08", "Linked-component recovery"),
    ("09", "STL units and per-body exports"),
    ("10", "Background execution, cancellation and responsiveness"),
    ("11", "Data integrity and failure recovery"),
    ("12", "Credential security and privacy"),
    ("13", "Restoring an earlier design version"),
    ("14", "Duplicate installation and add-in lifecycle"),
    ("15", "User interface and branding"),
    ("16", "Network interruption"),
    ("17", "Community Store compatibility"),
    ("18", "macOS"),
    ("19", "Usability with people new to Git"),
    ("20", "Final release packaging and documentation accuracy"),
])


def read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def problems(criteria: Sequence[Dict[str, str]], steps: Sequence[Dict[str, str]]) -> List[str]:
    found: List[str] = []
    step_ids = [s["step"] for s in steps]
    if len(set(step_ids)) != len(step_ids):
        found.append("steps.csv: duplicate step numbers")
    seen = set()
    for row in criteria:
        cid = row.get("id", "")
        where = f"criteria.csv {cid or '(no id)'}"
        if set(row) != set(FIELDS):
            found.append(f"{where}: columns must be exactly {FIELDS}")
            continue
        if not cid or cid in seen:
            found.append(f"{where}: missing or duplicate id")
        seen.add(cid)
        if row["workflow"] not in WORKFLOWS:
            found.append(f"{where}: unknown workflow {row['workflow']!r}")
        if row["mandatory"] not in MANDATORY:
            found.append(f"{where}: mandatory must be one of {MANDATORY}")
        if row["status"] not in STATUSES:
            found.append(f"{where}: status must be one of {STATUSES}")
        if row["step"] not in step_ids:
            found.append(f"{where}: unknown step {row['step']!r}")
        for key in ("requirement", "procedure", "expected"):
            if not row[key]:
                found.append(f"{where}: {key} is empty")
        if row["status"] in ("Pass", "Fail") and not row["evidence"]:
            found.append(f"{where}: a {row['status']} result needs evidence")
        if row["status"] == "Fail" and not row["defect"]:
            found.append(f"{where}: a failure needs a defect id")
    covered = {row["workflow"] for row in criteria}
    for code, name in WORKFLOWS.items():
        if code not in covered:
            found.append(f"workflow {code} ({name}) has no criteria")
    return found


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    keep = "".join(c for c in heading.lower() if c.isalnum() or c in " -_")
    return keep.replace(" ", "-")


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>")


def render_matrix(criteria: Sequence[Dict[str, str]]) -> str:
    out = io.StringIO()
    counts = Counter(row["status"] for row in criteria)
    mandatory = [r for r in criteria if r["mandatory"] == "yes"]
    out.write("# Consolidated acceptance matrix\n\n")
    out.write("<!-- Generated by scripts/acceptance.py from tests/acceptance/criteria.csv. Don't edit. -->\n\n")
    out.write("Every live acceptance criterion for 1.0, organised by user workflow. The record is\n")
    out.write("[`acceptance/criteria.csv`](acceptance/criteria.csv) (open it in a spreadsheet); the\n")
    out.write("order to run them in is [`MANUAL_CHECKLIST.md`](MANUAL_CHECKLIST.md). A criterion is\n")
    out.write("only *Pass* when it was seen in real Fusion (or on GitHub) and the evidence is recorded:\n")
    out.write("simulated tests never count.\n\n")
    out.write(f"**Status:** {len(criteria)} criteria ({len(mandatory)} mandatory) — ")
    out.write(", ".join(f"{s}: {counts.get(s, 0)}" for s in STATUSES) + ".\n\n")
    out.write("| Workflow | Criteria | Mandatory | Pass | Fail | Blocked | Not Run |\n|---|---|---|---|---|---|---|\n")
    for code, name in WORKFLOWS.items():
        rows = [r for r in criteria if r["workflow"] == code]
        c = Counter(r["status"] for r in rows)
        out.write(f"| [{code}. {name}](#{_slug(code + '. ' + name)}) | {len(rows)} | {sum(r['mandatory'] == 'yes' for r in rows)} | "
                  f"{c.get('Pass', 0)} | {c.get('Fail', 0)} | {c.get('Blocked', 0)} | {c.get('Not Run', 0)} |\n")
    for code, name in WORKFLOWS.items():
        out.write(f"\n<a id=\"{code}\"></a>\n\n## {code}. {name}\n\n")
        for row in (r for r in criteria if r["workflow"] == code):
            flag = "" if row["mandatory"] == "yes" else " *(if available)*"
            out.write(f"### {row['id']}{flag} — {row['status']}\n\n")
            out.write(f"- **Requirement / risk:** {row['requirement']}\n")
            out.write(f"- **Prerequisites:** {row['prerequisites'] or '—'} (run in campaign step {row['step']})\n")
            out.write(f"- **Procedure:** {row['procedure']}\n")
            out.write(f"- **Expected:** {row['expected']}\n")
            out.write(f"- **Actual:** {row['actual'] or '—'}\n")
            out.write(f"- **Evidence:** {row['evidence'] or '—'}\n")
            out.write(f"- **Defect:** {row['defect'] or '—'}\n\n")
    return out.getvalue()


def render_campaign(criteria: Sequence[Dict[str, str]], steps: Sequence[Dict[str, str]]) -> str:
    out = io.StringIO()
    out.write("# Live verification campaign (manual Fusion checklist)\n\n")
    out.write("<!-- Generated by scripts/acceptance.py from tests/acceptance/. Don't edit. -->\n\n")
    out.write("Run this in **real Fusion on Windows** before releasing (CONTRIBUTING → Releasing). The\n")
    out.write("automated tests run the dialog against *simulated* Fusion objects (`tests/fakes/adsk`);\n")
    out.write("this list covers what only real Fusion, GitHub and people can show.\n\n")
    out.write("**A release is not published until every mandatory criterion passes**, or its failure is\n")
    out.write("recorded with a maintainer decision. Criteria marked *(if available)* need something you may\n")
    out.write("not have (the Community Store, a Mac, a second computer). macOS is Experimental.\n\n")
    out.write("The steps form one campaign, in this order: each leaves Fusion in the state the next one\n")
    out.write("needs. It starts from the previous public release (0.4.0), so the upgrade, migration and\n")
    out.write("same-session update checks happen naturally. Expect about three hours for steps 0–16;\n")
    out.write("usability sessions (step 18) are separate.\n\n")
    out.write("**Record results** in [`acceptance/criteria.csv`](acceptance/criteria.csv): *actual*,\n")
    out.write("*evidence* (screenshot or log file name, commit link), *status* (Pass, Fail, Blocked,\n")
    out.write("Not Run) and *defect* (an issue number for every failure). Then run\n")
    out.write("`python scripts/acceptance.py render`. The [matrix](ACCEPTANCE_MATRIX.md) shows the same\n")
    out.write("criteria by workflow, with the totals.\n\n")
    out.write("| Item | Value |\n|---|---|\n| Add-in version (candidate ZIP name and SHA-256) | |\n")
    out.write("| Previous version installed for the upgrade test | |\n| Fusion build (Help → About) | |\n")
    out.write("| Windows version | |\n| Date, tester | |\n")
    for step in steps:
        out.write(f"\n## {step['step']}. {step['title']}\n\n")
        if step.get("setup"):
            out.write(step["setup"].replace("\\n", "\n") + "\n\n")
        for row in (r for r in criteria if r["step"] == step["step"]):
            flag = "" if row["mandatory"] == "yes" else " *(if available)*"
            out.write(f"- [ ] **{row['id']}**{flag} {row['procedure']} **Expected:** {row['expected']}\n")
    return out.getvalue()


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("check", "render", "summary"))
    args = parser.parse_args(list(argv))
    criteria, steps = read_csv(CRITERIA), read_csv(STEPS)
    found = problems(criteria, steps)
    if args.command == "summary":
        counts = Counter(row["status"] for row in criteria)
        print(f"{len(criteria)} criteria: " + ", ".join(f"{s} {counts.get(s, 0)}" for s in STATUSES))
        mandatory_open = [r["id"] for r in criteria if r["mandatory"] == "yes" and r["status"] != "Pass"]
        print(f"Mandatory not yet passed: {len(mandatory_open)}")
        return 0
    if found:
        print("\n".join(found))
        return 1
    renders = {MATRIX_MD: render_matrix(criteria), CAMPAIGN_MD: render_campaign(criteria, steps)}
    if args.command == "render":
        for path, text in renders.items():
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
        return 0
    stale = [p for p, text in renders.items()
             if not p.exists() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != text]
    if stale:
        print("Out of date (run python scripts/acceptance.py render): "
              + ", ".join(str(p.relative_to(ROOT)) for p in stale))
        return 1
    print(f"Acceptance matrix OK: {len(criteria)} criteria in {len(steps)} steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
