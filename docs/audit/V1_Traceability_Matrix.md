# v1.0 requirements traceability matrix

Every finding in the v1.0 readiness audit's backlog (§N of the
[audit report](FusionToGitHub_v1_Audit_Report.md)), traced to where it was
addressed, the automated evidence, and the live acceptance criteria that
still have to confirm it in real Fusion ([acceptance matrix](../../tests/ACCEPTANCE_MATRIX.md)).
State as of 0.9.0 (1.0.0 release candidate 1), 2026-11-28.

**Status values**
- **Done:** implemented, with automated evidence, and no live check needed
  (or the live check is listed only as a release smoke test).
- **Done, live pending:** implemented and tested automatically (against
  simulated Fusion where Fusion is involved); not yet confirmed live.
- **Partial:** partly addressed; the remainder is stated.
- **Deferred:** intentionally after 1.0, with the reason.
- **Maintainer:** needs a repository setting or decision only the maintainer can make.

Test files are in `tests/unit/` unless a path is given; `T_…` ids are in
`tests/test_runner.py`.

## Release integrity and packaging

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| PKG-01 | 0.3.2 Latest, empty, mismatched | 0.3.3 | Done | 0.3.3 released with asset; 0.3.2 marked pre-release | — |
| PKG-02 | No pre-publication gate | 0.3.3 | Done | `release.yml` draft-only, `check_release.py` | P1 |
| PKG-03 | Weak package validator | 0.3.3 | Done | `scripts/package.py validate` (exact file set, ID, imports); `test_package_isolation.py` | P1 |
| PKG-04 | Dispatch artifact | 0.3.3 | Done | Release workflow `workflow_dispatch` dry run | — |
| PKG-05 | Committed stale ZIP | 0.3.3 | Done | No ZIP tracked; `dist/` ignored | — |
| PKG-06 | Tag only main SHAs | 0.3.3 | Done | `check_release.py --require-on-main` in `release.yml` | — |
| PKG-07 | Draft-first / immutable releases | 0.3.3 | Partial / Maintainer | Draft-first done; immutable releases **on** (GitHub API); a tag ruleset is not configured (only a `main` ruleset) | — |
| PKG-08 | Versioned asset name | 0.3.3 | Done | `Push_To_GitHub-<version>.zip` | — |
| PKG-09 | Exclude dev tools | 0.3.3 | Done | `EXCLUDED_FILES` in `package.py` | — |
| SEC-06 | Release permissions, reproducibility, provenance | 0.3.3 | Done | Pinned actions, minimal permissions, attestation, byte-reproducible ZIP | P1 |
| DOC-05 | CHANGELOG, credit, withdrawn note | 0.3.3 | Done | CHANGELOG (Keep a Changelog), DiegoV71 credited | P2 |
| OSS-02 | Dev setup / releasing docs | 0.3.3, 0.8.0 | Done | CONTRIBUTING (setup, checks, releasing, Community Store) | — |

## Data integrity (Git pipeline)

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| REL-01 | Force push / remote overwrite | 0.3.3, 0.4.0 | Done | Force push removed; fast-forward only; `T_NOFORCE`, `T_PIPE_09` | — |
| ARCH-05 | Worktree-independent commit path | 0.4.0 | Done | Temporary index + `commit-tree`; `T_PIPE_01–05` | C6 |
| REL-05 | Rebases the user's branch | 0.4.0 | Done | No checkout or rebase; `T_PIPE_03` snapshot (now incl. `.git/config`, HEAD, hooks) | C6 |
| SEC-01 | Publishes private local commits | 0.4.0 | Done | Commits built on GitHub's tip; `T_PIPE_03` | — |
| REL-02 | Wrong / stranded stash | 0.4.0 | Done | No stash used (ARCH-05) | — |
| REL-03 | Locale decoding | 0.4.0 | Done | `LC_ALL=C`, UTF-8 decoding; non-ASCII tests | — |
| REL-04 | False "restored"; CLI rc 0 | 0.4.0 | Done | Truthful results; CLI exit codes tested | — |
| REL-06 | Timeouts / prompts / UI blocking | 0.4.0, 0.6.0 | Done, live pending | Timeouts on every git call, `GIT_TERMINAL_PROMPT=0`, background push; `T_PIPE_12`, `test_push_worker.py`. Residual: new-repository clone on the main thread (R-04) | I1, F2, F4 |
| REL-07 | Failure residue on the user branch | 0.4.0 | Done | Nothing written locally; temporary ref removed even if cleanup fails (`test_release_review_fixes.py`) | — |
| REL-08 | Detached HEAD restore | 0.4.0 | Done | Moot: HEAD never changed (ARCH-05) | — |
| REL-09 | In-progress operation guard | 0.4.0 | Done | Moot: working tree and index never touched | — |
| REL-10 | Setup re-points origin | 0.4.0 | Done | Asks before re-pointing; `test_dialog.py` | B1 |
| REL-12 | `.gitattributes` / line endings | 0.4.0 | Done | `hash-object --no-filters`; `.gitattributes` on bootstrap; `T_PIPE_15` | — |
| REL-14 | `stash pop --index` | 0.4.0 | Done | Moot (no stash) | — |
| BUG-08 | `--` separators / ref validation | 0.4.0, 0.7.0 | Done | `--` before paths, `check-ref-format`, `branch_name_problem`; remote SHAs validated (0.9.0) | — |
| UX-09 | Override to main warning | 0.4.0 | Done | Distinct question for the default branch | I5 |
| PERF-01 | `push -u` growth | 0.4.0 | Done | No `-u`, no local branches created | — |
| TEST-02 | Failure-path test suite | 0.4.0 | Done | `tests/test_runner.py` pipeline cases | — |
| DOC-03 | Public-exposure and size warnings, size gate | 0.4.0 | Done | 100 MB refusal, 50 MB question, publication notice; `T_PIPE_13` | B4 |
| BUG-04 | Partial export reported as success | 0.6.0 | Done, live pending | All-or-nothing (`export_checks`); `test_dialog_exports.py` | J6 |
| R-24 | Design folders across profiles (risk) | 0.7.0 | Done, live pending | HISTORY markers; `test_core_design_folders.py`, `test_dialog_ux.py` | U14 |

## Security and privacy

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| SEC-02 | Helper persistence / override | 0.4.0 | Done | Helpers reset, one-host inline helper; `T_CORE_03` | D3 |
| SEC-03 | Token in URL | 0.4.0 | Done | Refused and redacted; `T_CORE_05` | B2 |
| SEC-04 | Token visible to hooks / any host | 0.4.0–0.9.0 | Done, live pending | Hooks off, `GIT_ALLOW_PROTOCOL`, destination checks, token out of environments (E4), alternate-refs and maintenance off; `test_core_cancel_hooks.py`, `test_release_review_fixes.py`, r21 probes | D3, R1, R2, S1 |
| SEC-05 | Symlink / junction containment | 0.4.0 | Done | Moot: nothing is written into the repository folder (ARCH-05); the credential sweep doesn't follow links | — |
| SEC-07 | Masked PAT input | 0.5.0 | Done, live pending | `isPassword`; `test_dialog.py` | D1, H5 |
| SEC-09 | File permissions / log redaction | 0.4.0 | Done, live pending | 0600 files, redacting formatter, end-to-end token scan (0.9.0) | G1 |
| SEC-10 | Document hook execution | 0.4.0 | Done | SECURITY.md | — |
| SEC-11 | CLI token via env / getpass | 0.4.0 | Done | `push_cli.py` env var or `getpass` | — |
| SEC-12 | Copilot agent / prompt files | 0.5.0 | Done | Removed (decision Q13) | — |
| SEC-08 | Private vulnerability reporting | — | Maintainer | Off (GitHub API, 2026-11-28); SECURITY.md has the fallback | — |
| COMP-03 | Privacy policy + notice | 0.4.0 | Done, live pending | PRIVACY.md, in-app link, notice once per repository | F1, B4, G2 |
| DOC-06 | SECURITY.md corrections | 0.4.0, 0.8.0, 0.9.0 | Done | Claims re-checked by the S7 security review | — |
| R-21 E4 | Token in process environments (risk) | 0.7.0 | Done, live pending | Per-command credential file; `TokenOutOfEnvironmentTests` | S1, D3 |

## Fusion integration and exports

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| TEST-01 | Fake-adsk add-in tests | 0.5.0 | Done | `tests/fakes/adsk` with 34 documented assumptions | all H-items |
| BUG-02 | F3Z / xref | 0.6.0, 0.9.0 | Done, live pending | Detection + question (0.6.0); `.f3z` export with fallback (0.9.0); `test_fusion_export.py` | J1, J2 (required for 1.0) |
| COMP-01 | macOS git discovery and sign-in | 0.6.0 | Done, live pending | Homebrew-first discovery, Check My Setup helper check; macOS Experimental | M1–M3 |
| COMP-05 | Duplicate installs / migration | 0.3.3, 0.6.0 | Done, live pending | Duplicate guard; `two_versions` scenario | K6, H16 |
| ARCH-01 | Package-relative imports | 0.6.0 | Done, live pending | `test_package_isolation.py` with real 0.3.3/0.4.0 tags | K1, K3, K2 |
| BUG-03 | STEP option no-op | 0.7.0 | Done | Option removed | U5 |
| BUG-05 | STL units / per body | 0.6.0 | Done, live pending | `test_fusion_export.py` | J3, J4, J5 |
| BUG-06 | Filename regex / portable names | 0.6.0, 0.9.0 | Done, live pending | `portable_names`; version-suffix fix (0.9.0) | J7 |
| BUG-07 | addCommand positionID | 0.6.0 | Done, live pending | Control id passed as id; dedupe in all panels; `test_addin_lifecycle.py` | K4, K9, H10 |
| BUG-09 | Misnamed API members | 0.9.0 | Done, live pending | `isBackgroundTranslucent`; `CriticalLogLevel` looked up defensively | C5 |
| UX-03 | Active document validation; Fusion version | 0.7.0 | Done, live pending | Design line, version in HISTORY and summary | U6 |
| COMP-06 | Licence-tier export hints | — | Partial / Deferred | A failed IGES/SAT export stops the backup with Fusion's own reason; no licence-specific hint. Live C7 records what happens | C7 |
| COMP-07 | Windows git discovery | 0.6.0 | Done | `git_candidates` (Program Files, LocalAppData, GitHub Desktop) | U12 |
| REL-11 | Synced-folder warning | 0.6.0 | Done, live pending | `synced_folder_service` | L1, L2 |

## Architecture and quality

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| ARCH-02 | Extract push_controller | 0.5.0 | Done | `push_controller.py`, 91 % coverage | — |
| ARCH-03 | Config schema + edit/remove | 0.5.0 | Done, live pending | `settings_store.py` (schema, atomic, migrations) | E1–E4, A3, A4 |
| ARCH-04 | Dead code / stale docs | 0.5.0, 0.8.0 | Done | Stale documents removed in 0.8.0 | — |
| REL-13 | Config load robustness | 0.5.0 | Done, live pending | Corrupt/newer files preserved; `test_settings_store.py` | F3 |
| TEST-03 | Test isolation / cleanup | 0.5.0 | Done | GitSandbox, tempdir guard in CI | — |
| TEST-05 | Weak tests / manual criteria | 0.5.0, 0.9.0 | Done | Assertion lint in the coverage gate; criteria in the acceptance matrix are measurable | — |
| QUAL-01 | mypy on pure modules | — | Deferred | Not added; ruff and per-module coverage gates cover correctness. Post-1.0 | — |
| QUAL-02 | Broad excepts surfaced | 0.5.0 | Partial | Excepts at Fusion handler boundaries remain by design (an escaping exception breaks the dialog) and are logged; errors reach the user through the catalog | — |

## User experience

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| UX-01 | Single-history default | 0.7.0 | Done, live pending | `test_dialog_ux.py` | U8–U10 |
| UX-02 | validateInputs | 0.7.0 | Done, live pending | `test_dialog_ux.py` | U1 |
| UX-04 | Error catalog / no tracebacks | 0.7.0 | Done, live pending | `error_catalog.py`; every dialog test checks for tracebacks | U13 |
| UX-05 | Open on GitHub / success content | 0.7.0 | Done, live pending | `LinkTests` | U11 |
| UX-06 | Dialog information architecture | 0.7.0 | Done, live pending | S5 report §4 | U1–U7, X1–X4 |
| UX-07 | First-run preflight | 0.7.0 | Done, live pending | `setup_check.py`; `CheckMySetupTests` | U12, U15, N1 |
| UX-08 | Single display name | 0.3.3 | Done | "Push to GitHub"; `T_NAME` | A2 |
| UX-10 | Empty required message | 0.7.0 | Done, live pending | `ValidationTests` | U2 |
| UX-11 | Update / uninstall docs | 0.8.0 | Done, live pending | `docs/INSTALL.md` | W1, W4 |
| COMP-02 | Original icon + resources | 0.7.0 | Done, live pending | `scripts/make_icons.py`, icon tests | U3, W6 |
| COMP-13 | Forced promotion | 0.7.0 | Done, live pending | `test_addin_lifecycle.py` | U4 |

## Documentation, community and distribution

| ID | Finding | Version | Status | Implementation / evidence | Live |
|---|---|---|---|---|---|
| DOC-01 | Install folder name | 0.3.3, 0.8.0 | Done | Docs guard rejects `AddIns/FusionToGitHub` | W1 |
| DOC-02 | Destructive troubleshooting advice | 0.3.3, 0.8.0 | Done | Rewritten; docs guard rejects `reset --hard` | — |
| DOC-04 | Restore procedure | 0.8.0 | Done, live pending | `docs/RESTORE.md` | W2, V1, X1–X3 |
| DOC-07 | Docs consolidation | 0.8.0 | Done | `docs/README.md`; 12 documents removed | — |
| DOC-08 | Overstated claims | 0.8.0 | Done | Independent documentation review | P2 |
| DOC-09 | Prerequisites consolidated | 0.8.0 | Done | `docs/INSTALL.md` → What you need | W1 |
| DOC-10 | Names / labels / icon in docs | 0.8.0 | Done, live pending | Labels checked against code | W3 |
| DOC-11 | Remove-repo / uninstall / glossary | 0.8.0 | Done | User guide, install guide | W4 |
| OSS-01 | Community health files | 0.8.0 | Done | GitHub community profile 100 % | — |
| OSS-03 | Repository settings hygiene | — | Maintainer | Wiki on; private vulnerability reporting off; tag ruleset missing; description outdated after 0.7.0 (S6 report §5) | — |
| COMP-08 | Store artwork / screenshots | 0.8.0 | Partial | `community-store.json` with icon; screenshots not yet captured (real Fusion only) | W5, W6 |
| COMP-09 | Trusted-source request | — | Done | Owner already trusted (`trusted-stores.json`) | — |
| COMP-11 | Trademark disclaimer | 0.8.0 | Done | README footer, SUPPORT | — |
| FEAT-01 | Non-GitHub hosts untested | 0.8.0 | Done | README *Other Git servers* | — |
| TEST-04 | Native Fusion + macOS evidence | — | Pending | The live campaign (acceptance matrix) | all |

## Autodesk App Store track (after 1.0, decision Q7/Q8)

| ID | Finding | Status |
|---|---|---|
| COMP-04 | Autodesk EUA | Deferred (Autodesk track) |
| COMP-10 | Load-time measurement | Deferred for the store; measured in the campaign (P3) |
| COMP-12 | Autodesk submission kit | Deferred (Autodesk track) |

## Maintainer decisions and risks

The maintainer's decisions (Q1–Q17 and those of 2026-11-26/27/28) are
recorded in the audit report's decision log and the
[risk register](../RISK_REGISTER.md); every open risk names the live criteria
that would resolve it.
