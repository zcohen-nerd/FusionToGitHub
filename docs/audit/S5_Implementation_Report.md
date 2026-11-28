# FusionToGitHub — S5 Implementation Report

**Sprint:** S5 — User experience and branding (development version 0.7.0)
**Branch / PR:** `s5-ux-branding` → `main`
**Date:** 2026-11-28
**Strategy:** the maintainer's feature-completion decision of 2026-11-28 applies. S5, S6 and the S7 preparation are built one after another. Live Fusion verification is gathered into one consolidated campaign at the end, so this sprint merges after its automated gates and an independent review. 0.6.0 and 0.7.0 stay unpublished; 0.4.0 remains the public release.
**Status:**
- **Implemented**. Local gates pass: 275 unit tests (3 skipped) and 35 integration tests, ruff, the release check (0.7.0), the docs check, the icon check, and the coverage gate (every module except `credentials.py`, which only CI's Windows job measures fully). CI results are on the pull request.
- **Not verified in real Fusion.** Nothing in this report has been checked live. The new live checks are U1–U16 in `tests/MANUAL_CHECKLIST.md` (step 4a).

---

## 1. Scope delivered

| Requirement (maintainer brief / audit) | Delivered |
|---|---|
| Continuous revision history as the default for new profiles (UX-01, decision 1) | New profiles get `historyMode: "single"`, `exportSubfolder: "designs"`. Backups go to the repository's default branch (or Advanced → *Backup branch*) under `designs/<design>/` |
| Snapshot branches kept as an advanced option | Advanced → *Separate branch per backup*, with the branch template and *Use this branch instead*. These are visible only in that mode |
| Existing configurations preserved | No migration and no schema change. A profile without `historyMode` (any profile saved before 0.7.0) is read as snapshot mode. Its commit template has no `{message}`, so typed messages work as before. The checkbox shows the mode |
| Simpler workflow for people with no Git experience (UX-06) | The basic view shows the design (with its Fusion version), the repository, *Saves to*, *What changed?* and *Files to include* with descriptions. Git details moved to Advanced, and logs and privacy to *Help & Privacy*. OK reads *Back up now*. Returning users start on their saved repository |
| Confirmation disabled until inputs are valid (UX-02) | `validateInputs` handler. OK is disabled while any problem remains, and a summary line lists them in words. `execute` checks again, defensively |
| Actionable plain-language messages (UX-04) | `error_catalog.py`: 12 failure classes, each with a plain first line and a next step; Git's text is kept under "Technical details". No traceback reaches a message box: every dialog test checks this, and the entry point's handlers were changed too |
| Open on GitHub and Copy Link (UX-05) | The success summary shows the repository, branch › folder, short commit, Fusion version and files. Then Yes opens the folder on GitHub, No copies the link (with a hand-copy fallback), and Cancel closes |
| First-time setup diagnostics, Check My Setup (UX-07) | `setup_check.py`. Local checks cover Git presence and version (≥ 2.30 recommended), identity, the sign-in helper, the folder, the origin against the saved address, the synced folder and the stored-token conditions. A read-only connection test (`git ls-remote`) runs on the background worker. With no saved repository, blocking problems are shown when the dialog opens |
| Explain missing dependencies, auth failures, repository problems | The catalog covers auth, not found, network, TLS, timeout, lock, size, protected branch, disk, missing Git and identity. Check My Setup has the same coverage |
| R-24: design folders across profiles | A hashed design marker in `HISTORY.md`; folders are checked against GitHub before each commit (§3) |
| Dialog organisation, advanced settings, accessibility | §4 |
| UX-08 single display name | Already done in S0 ("Push to GitHub"). The tooltip is rewritten |
| UX-10 required, empty message | "What changed?" starts empty, is required, and is no longer stored (`lastCommitMessage` is removed on the next push) |
| COMP-13 forced promotion | `isPromoted = True` removed; `isPromotedByDefault` kept |
| BUG-03 STEP protocol no-op (1.0 Definition of Done) | The option is removed and saved values are ignored |
| Branding (COMP-02) | §5 |

Not in scope and not done: documentation rewrite, screenshots and store artwork beyond the icon set (S6); the R-21 E4 token channel (separate security work after S5); R-06 archive research (S7 preparation).

## 2. Architecture changes

```
dialog (main thread)                        controller / core (no Fusion)
───────────────────────                     ──────────────────────────────
validateInputs → validation_problems()      new_profile_settings(), compose_commit_message()
OK → export → controller.plan()  ─────────► PushPlan(+ target_branch, design_id, design_folder,
                                                       export_template, source_files, fusion_version)
bridge.start(plan, job)          ─────────► worker: controller.execute(plan) → push_export(..., relocate=…)
                                                       _choose_design_folder() against the base commit
done ─► job.on_result → controller.record_result()  (re-reads settings; remembers a moved folder)
     ─► success_text() + Open on GitHub / Copy Link (github_links)
Check My Setup → setup_check.local_checks() (main thread)
               → bridge.start(ConnectionTest)  ─► check_connection() (ls-remote, token-safe)
               → format_report()
errors anywhere ─► error_catalog.explain() / unexpected_error()
```

- **No new Fusion API surface on the worker thread.** The connection test reuses `PushWorker` and `WorkerBridge`. A `PushJob` now has a `kind`, plus the local checks as plain dicts.
- **`token_session()`** factors out S4's token safeguards: the host binding, the repository proxy/TLS refusal, the destination check, and hooks disabled. Pushes and the connection test both use it, so the test can't be a weaker path for the token.
- **New modules:** `error_catalog.py`, `github_links.py`, `setup_check.py`, all Fusion-free and shipped. They import siblings relatively (R-25 rule) and are listed in `scripts/package.py`.

## 3. R-24: design folders checked against GitHub

- Each `HISTORY.md` gets `<!-- fusion-to-github design: <key> -->` after its title. `<key>` is the first 16 hex digits of SHA-256 of the design's Fusion id: stable, and it doesn't publish the id (PRIVACY.md updated).
- Before building the commit, `push_export` lists the folders at the design-folder level on the base commit and reads each `HISTORY.md` marker. Then:
  - it keeps its folder if the marker there matches or there is none;
  - it moves to a folder that already carries its marker;
  - otherwise, if its folder belongs to another design, it takes the next free `<name> (n)`.
- After a successful push, the main thread records the moved folder in the profile. It re-reads the file first, so it doesn't overwrite a dialog opened meanwhile. GitHub's markers stay the source of truth if that save fails.
- **Race:** two pushes that pick the same free name are serialised by the fast-forward-only push. The loser is rejected, rebuilds on the new tip, and the check re-runs.
- **Limit:** histories from before 0.7.0 have no marker, so they are kept by whichever design uses them next. More limits, and the review hardening, are in R-24 of the risk register.

## 4. Dialog organisation and accessibility review

| Area | Before | After |
|---|---|---|
| Groups | Repository, Commit Message, Export Formats, Templates, Advanced, Logging & Privacy (six concepts) | Design line; Repository (with Saves to, Edit/Remove, Check My Setup); What changed?; Files to include; Advanced; Help & Privacy |
| Labels | "GitHub URL", "Repository Name", "Local Folder", "Browse…", format codes `f3d`, `stl` | "GitHub address", "Name in this list", "Local folder", "Choose folder…", "Fusion design (.f3d): the full editable design", … |
| Placeholders | `{filename}`, `{timestamp}` unexplained | Every template field's tooltip explains its placeholders |
| Status | Emoji-only prefixes in some messages | Every status in Check My Setup is a word (`[OK]`, `[Check]`, `[Problem]`, `[Note]`). The validation summary is a sentence. Emoji are no longer the only carrier of meaning in the new texts |
| Errors | Raw Git stderr, "See the messages above", tracebacks | Plain first line and next step, details below, no tracebacks |
| Keyboard / screen reader | Fusion's own command dialog handles focus and reading; the add-in doesn't change it | Unchanged. Message boxes are plain text and readable by screen readers. Not tested with a screen reader (live check, recorded as an open item) |
| Colour | Not used for meaning | Not used for meaning; the icon doesn't rely on colour to be recognised |

Remaining accessibility limits, all from Fusion's API:
- Message-box buttons are fixed to Yes/No/Cancel, so Open/Copy/Close are explained in the text.
- There is no rich text and no control over focus order.
- Tooltips appear only on hover.

## 5. Branding

- **Source:** the approved master `Assets/Branding/Icon-Master.png` (1254 px). It stays untracked at the maintainer's choice; the maintainer decides whether to commit it.
- **Vector redraw:** `scripts/make_icons.py` holds the geometry: three isometric faces, a three-node branch and the navy square. It writes the SVGs and every PNG with a dependency-free 4 × 4 supersampling rasteriser, so the output is byte-reproducible. Colours were sampled from the master.
- **Small sizes:** a *small* drawing (a larger cube, a thicker branch, no white node centres) is used at 16 and 32 px. It was checked at real pixel size on light and dark backgrounds.
- **Outputs:**
  - toolbar `src/resources/{16x16,16x16@2x,32x32,32x32@2x}.png`, which are packaged and passed to `addButtonDefinition`;
  - `src/AddInIcon.svg`, now pure vector (it was a 75 KB PNG embedding the Invertocat);
  - store sizes 120, 256 and 512 px.
- **Documentation:** `branding/README.md`.
- **Tests:** `--check` that the committed files match the generator; sizes; no raster inside the SVGs.
- **Not verified:** appearance in Fusion's toolbar and Add-Ins list (live check U3), and whether the Community Store picks up `resources/32x32@2x.png` (S6, together with `community-store.json`).

## 6. Tests

| Suite | Before S5 | After S5 |
|---|---|---|
| Unit (incl. simulated-Fusion dialog tests) | 222 | 275 (3 skipped where release tags or the real vault are absent) |
| Integration (`tests/test_runner.py`) | 35 | 35 |

New test files:
- `test_ux_helpers.py`: the catalog, links, setup checks (fake Git plus a real `ls-remote`), history modes, commit messages, branch names, the version text and the icons.
- `test_dialog_ux.py`: OK gating, single history on `main`, the backup branch, legacy snapshot profiles, switching modes, unsaved changes, Open/Copy/fallback, Check My Setup (OK and failing), first run, and R-24 across two profiles.
- `test_core_design_folders.py`: markers against real Git, including relocation, rediscovery, unmarked histories and folders without histories.

Harness changes:
- `press_ok` refuses a disabled OK (assumption 27).
- `push()` types "What changed?".
- Every dialog test fails if a traceback is shown.
- The clipboard is never touched (it's recorded instead).
- The "Open it on GitHub?" question defaults to Cancel unless a test scripts it.

New simulated-Fusion assumptions: 27–32 in `tests/fakes/README.md`.

## 7. Risk register changes

- R-24 → Mitigated.
- R-20 → Mitigated.
- R-14 now states the minimum Git version.
- New: R-27, backups added straight to a repository's main branch. Mitigated by the *Saves to* line, the Backup branch option, the protected-branch explanation and fast-forward-only commits.

## 8. Live checks added

U1–U16 (`tests/MANUAL_CHECKLIST.md`, step 4a): OK gating, the empty message, the icon in both themes and at high DPI, user promotion, format labels, the Fusion version line, Saves to, a running history, a backup branch, legacy snapshots, Open/Copy, Check My Setup, network-error wording with no tracebacks anywhere, R-24, first run without Git, and a protected branch.

## 9. Independent reviews and what changed

Two independent reviews ran on the S5 diff:
- a correctness and data-integrity review;
- a security and privacy review.

Neither found a blocker. The token guarantees (R-07, R-21, R-23) were confirmed unchanged: `token_session` keeps the order and the refusals, `check_connection` redacts, and Check My Setup fails closed when the stored token can't be used. Findings and fixes:

| # | Finding | Severity | Fix | Regression test |
|---|---|---|---|---|
| C1 | R-24 skipped non-ASCII folder names (Git quoted them in `ls-tree` output) | Important | `ls-tree -r -l -z` | `test_non_ascii_folder_names_are_checked_too` |
| C2 | A design saved after its first backup moved to a new folder (its provisional `name:` id was in the marker) | Important | Provisional ids don't write a marker; they still never write into another design's folder | `test_a_design_saved_after_its_first_backup_keeps_its_folder`, `test_an_unsaved_design_does_not_write_into_another_designs_folder` |
| C3 | No R-24 check when the template embeds the name in a longer folder name | Minor | Documented as a limit (R-24) | — |
| C4 | Folders differing only in case were treated as different | Minor | Same folder; a new name keeps the design's own case | `test_a_folder_differing_only_in_case_is_the_same_folder` |
| C5 | `{timestamp}` typed in "What changed?" was substituted | Minor | `{message}` is filled last (`commit_text`) | `HistoryModeTests`, `commit_message_parts` tests |
| C6 | A dialog opened during a push can overwrite the recorded folder | Minor | None needed: GitHub's markers stay authoritative (documented) | — |
| S1 | Marker spoofing through a design name or note | Medium | The marker only counts on its own line after the title | `test_a_design_name_or_message_cannot_claim_a_history`, `test_the_same_design_keeps_its_folder_whatever_its_name_says` |
| S2 | `git@HOST:` host not validated, so the link could open a different host | Medium/low | Host-name check; the built URL must keep that host | `GitHubLinkTests` |
| S3 | A hostile repository could make a push read without bound | Low/medium | HISTORY.md over 1 MB isn't read; at most 300 folders examined; one `cat-file` per folder | — (bounds in code) |
| S4 | Collaborator-planted marker folder | Low | Documented (write access implies full control) | — |
| S5 | `unexpected_error` didn't redact | Low | Redacted | `ErrorCatalogTests` |
| S6 | Check My Setup showed the raw `credential.helper` value | Low | Only the helper's name, redacted | `SetupCheckTests` |
| S7 | `clip`/`pbcopy` found through PATH; `.`/`..` in links | Low/info | Full system paths; such segments dropped | `GitHubLinkTests` |
| S8 | The marker links backups of one design across repositories | Info | Stated in PRIVACY.md and R-24 | — |

## 10. Known limitations and follow-ups

- No live verification (see the status at the top).
- The *Saves to* line shows `<folder>/<design>/` from the template as typed. A template containing `{timestamp}` is shown unexpanded.
- `Check My Setup` doesn't test whether the token's permissions allow writing (that needs a push or the GitHub API, which the add-in doesn't use). The first real backup is the test.
- Message-box button labels can't be changed by the API.

## 11. Coverage (local, Windows, both suites)

New modules: `error_catalog.py` 95.7 %, `github_links.py` 91.2 %, `setup_check.py` 92.5 % (gate thresholds 93, 88 and 90). `fusion_git_core.py` 89.2 %, `push_controller.py` 91.1 %, `push_dialog.py` 80.0 %, `fusion_bridge.py` 84.5 % (threshold raised from 81 to 83). The add-in layer group is at 79.6 % (minimum 74).
