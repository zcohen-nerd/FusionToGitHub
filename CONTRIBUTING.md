# Contributing to FusionToGitHub

Bug reports and pull requests are welcome. For a large change, please open an
issue first so we can agree on the approach.

## Development setup

You need Python 3.10+ and Git. No third-party Python packages are required to
run the add-in or its tests (`coverage` is optional, for the coverage gate).

| Check | Command |
|---|---|
| Git regression tests | `python tests/test_runner.py` |
| Unit tests (incl. the dialog against simulated Fusion) | `python -m unittest discover -s tests/unit` |
| Unusual Git config | set `GIT_CONFIG_GLOBAL` to `tests/hostile.gitconfig`, then run both suites |
| Coverage gate | see the Coverage job in `.github/workflows/ci.yml`; thresholds in `scripts/coverage_gate.py` |
| Lint | `pip install ruff==0.16.5`, then `ruff check src/ tests/ scripts/` |
| Docs links | `node .github/scripts/check-docs.mjs` |
| Release consistency | `python scripts/check_release.py` |
| Build the add-in ZIP | `python scripts/package.py build` (writes `dist/`) |

CI runs all of these on every pull request and uploads the built ZIP as a
`Push_To_GitHub-test-build` artifact you can install in Fusion.

### How the code is organised

| Module | Role | Fusion? |
|---|---|---|
| `Push_To_GitHub.py` | Entry point: `run`/`stop`, toolbar button | yes |
| `push_dialog.py` | The dialog: inputs, validation, events | yes |
| `fusion_export.py` | Exports the design; its name and stable id | yes |
| `addin_logging.py` | Log file, redaction, Clear Log | palette only |
| `fusion_bridge.py` | Main-thread side of a background push: progress, questions, summary, links | yes |
| `push_worker.py` | Runs a push (or Check My Setup's connection test) on a background thread | no |
| `push_controller.py` | The push workflow and repository Edit/Remove | no |
| `settings_store.py` | Versioned, atomic settings | no |
| `credentials.py` | Stored tokens (Windows Credential Manager) | no |
| `fusion_git_core.py` | Git: isolated commits, timeouts, credentials, design folders | no |
| `setup_check.py` | Check My Setup: local checks and the connection test | no |
| `error_catalog.py` | Plain-language explanations of errors | no |
| `github_links.py` | Links to a backup on GitHub; copying to the clipboard | no |
| `export_checks.py`, `portable_names.py` | Export file checks; portable file names | no |
| `dialog_helpers.py` | Small pure helpers | no |

Keep Fusion API calls in the first five. A push is planned on Fusion's main
thread (`PushController.plan`) and executed with Git only on a background
thread (`PushController.execute`, run by `push_worker`); keep `execute` and
everything it calls free of Fusion calls. Shipped modules import each other
relatively (`from . import x`); `fusion_git_core.py` imports nothing from the
package, because `push_cli.py` and `diagnostic.py` load it as a plain module.

Every message the user sees goes through `error_catalog` when it can contain
Git's or Python's own text, and no message box may show a traceback (the
dialog tests check this). The icons are generated: edit
`scripts/make_icons.py` and run it, never the PNGs (see `branding/README.md`).

### Testing rules

- Tests that need Fusion use the stand-ins in `tests/fakes/adsk`. They
  simulate Fusion, they don't prove it: anything that depends on how real
  Fusion behaves goes in [`tests/MANUAL_CHECKLIST.md`](tests/MANUAL_CHECKLIST.md).
- Tests never touch your real settings, logs, Credential Manager or global Git
  config. Use temp folders, `MemoryCredentialStore`, and
  `GIT_CONFIG_NOSYSTEM=1` plus an empty `GIT_CONFIG_GLOBAL` (see `GitSandbox`
  in `tests/unit/test_core_identity_history.py`). Never use a real host such
  as github.com in credential tests.
- Every test must assert something; the coverage gate fails tests that
  don't. Coverage minimums are per module and only go up.
- New risks go in [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md); none is
  accepted without the maintainer's explicit agreement.

## Pull requests

- Add or update tests for behaviour you change. The Git pipeline tests run
  against local repositories and never touch GitHub.
- For changes to the Fusion dialog, add tests against the simulated Fusion
  objects, and say in the PR what you checked by hand in real Fusion (see
  [`tests/MANUAL_CHECKLIST.md`](tests/MANUAL_CHECKLIST.md)).
- Update the docs in the same PR.
- Never include tokens, private designs or unredacted logs.
- The add-in must never force-push or rewrite history on GitHub; a test
  (`T_NOFORCE`) enforces this.
- External contributions are credited in the CHANGELOG with the contributor's
  GitHub handle and the PR number.

## Releasing

The version is set **once**, in `src/Push_To_GitHub.manifest`. Releases are
cut only from commits on `main`, and nothing is published automatically.

1. **Prepare the release in a pull request.**
   - Set `"version"` in `src/Push_To_GitHub.manifest`.
   - Set `VERSION` in `src/fusion_git_core.py` and the **Version** line in
     `README.md` to match.
   - Add `## X.Y.Z — YYYY-MM-DD` at the top of `CHANGELOG.md`, with credits.
   - `python scripts/check_release.py --tag X.Y.Z` must pass.
2. **Merge it** once CI is green.
3. **Tag the merged commit** with the bare version (no `v` prefix), which is
   what Fusion and the Community Store expect:
   ```sh
   git switch main && git pull
   git tag X.Y.Z && git push origin X.Y.Z
   ```
4. **The Release workflow** runs CI on the tag, checks that the tag matches
   the manifest and is on `main`, builds and validates the ZIP, attests it,
   and creates a **draft** release with the ZIP, its `.sha256` file and notes
   from the CHANGELOG. If any step fails, no release is created.
5. **Test the drafted ZIP.** Download it from the draft, install it in Fusion
   on Windows following the README, and work through
   [`tests/MANUAL_CHECKLIST.md`](tests/MANUAL_CHECKLIST.md). Review
   [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) for the release.
6. **Publish the draft** on GitHub. Check that the asset shows a SHA-256
   digest (`gh release view X.Y.Z --json assets`).

**If something is wrong**, delete the draft, fix it on `main`, and release the
next patch version. Never move or re-push a tag that has been pushed.

**Dry run:** *Actions → Release → Run workflow* on any branch builds and
uploads the ZIP as an artifact without creating a release. To rehearse the
whole flow, push a test tag to a fork.

**One-time repository settings** (maintainer, in GitHub settings): turn on
*Immutable releases*; add a tag ruleset that blocks updating or deleting
version tags; turn on *Private vulnerability reporting*.
