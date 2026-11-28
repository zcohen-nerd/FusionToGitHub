# Testing

How Push to GitHub is tested, and what each kind of test can and can't show.
Commands and CI jobs are in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Automated tests

| Suite | Command | What it covers |
|---|---|---|
| Unit tests | `python -m unittest discover -s tests/unit` | Every module, including the dialog, the add-in's start and stop, background pushes, updates in a running Fusion and the icons. Git commands run for real against temporary local repositories |
| Integration tests | `python tests/test_runner.py` | The Git pipeline end to end through the standalone CLI (`src/push_cli.py`), version consistency, display name, no force push, packaging |
| Unusual Git configuration | Both suites with `GIT_CONFIG_GLOBAL=tests/hostile.gitconfig` | Settings a user might have that could change Git's behaviour |
| Coverage gate | See the Coverage job in `.github/workflows/ci.yml` | Per-module minimums (`scripts/coverage_gate.py`); every test must assert something |

CI runs them on Windows, macOS and Ubuntu, with Python 3.10 to 3.12.

**Isolation.** Tests never touch your real settings, logs, Windows Credential
Manager, `%LOCALAPPDATA%`, or Git configuration, and never contact a real
server: they use temporary folders, an in-memory credential store, Git with no
system or global configuration, local "GitHub" repositories, and synthetic
tokens on fake hosts (`*.example.invalid`).

## Simulated Fusion

Fusion's API isn't available outside Fusion, so the dialog and add-in tests run
against stand-ins in `tests/fakes/adsk`. They prove the add-in's own logic is
right **if Fusion behaves as they assume**. Each assumption is listed in
[`tests/fakes/README.md`](fakes/README.md) and checked in real Fusion by the
manual checklist. A passing simulated test is never reported as verified in
Fusion.

## In real Fusion

[`MANUAL_CHECKLIST.md`](MANUAL_CHECKLIST.md) is the release gate: one ordered
session in real Fusion on Windows (and on macOS when available) that covers
installation, updates, every dialog feature, exports, background pushes,
stored tokens, lifecycle and the assumptions above. A release is published only
after its mandatory items pass, or each failure has a recorded maintainer
decision.
