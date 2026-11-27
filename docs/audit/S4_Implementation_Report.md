# FusionToGitHub — S4 Implementation Report

**Sprint:** S4 — Fusion Integration and Export Reliability (target 0.6.0)
**Branch / PR:** `feat/s4-fusion-integration` → PR #21. It is stacked on #20 (S3, 0.5.0), so its base is `feat/s3-testability`.
**Date:** 2026-11-27
**Status:**
- **Implementation complete.** All automated gates pass locally; the cross-platform CI result is in the closing note.
- **Not release-ready.** Nothing has been verified in real Fusion, and 0.6.0 must not be published until `tests/MANUAL_CHECKLIST.md`, including the new sections I–M, passes.

---

## 1. Baseline

| Item | State at sprint start |
|---|---|
| PR #20 (S3, 0.5.0) | Open, 13/13 checks green, mergeable, not merged |
| Releases | 0.4.0 Latest (immutable); 0.3.3; 0.3.2 pre-release (withdrawn note). 0.5.0 not released |
| Manual Fusion results | The maintainer ran 0.3.3 in Fusion ("worked perfectly") and saw "Push to GitHub" in the Add-Ins list. Neither 0.4.0 nor 0.5.0 has a recorded checklist run |
| Suites | 118 unit tests (3 skipped), 35 integration tests, coverage gate green in CI |
| Gaps in the Fusion stand-ins | They kept handlers strongly; custom events were synchronous; there was no thread check, no `destroy`/`validateInputs`, no value-type checks and no progress cancel |

**Implementation vs. release readiness.** S3 and S4 are implemented and pass their automated gates. Neither is release-ready, because the live Fusion checklist has not been run for 0.4.0 onward. This report claims no manual verification.

## 2. Architecture

```
main thread (Fusion)                                         worker thread (no Fusion calls)
──────────────────────────────────────────                   ───────────────────────────────
dialog OK ─► export (all-or-nothing, checks)
          ─► linked-component question
          ─► controller.plan(): notice, identity,
             token checks (host, repo proxy/TLS)
          ─► large-file question
          ─► bridge.start(plan) ───────────────────────────► PushWorker.run:
                                                               controller.execute(plan)
                                                               push_export(cancel=event)
custom event handler ◄─ app.fireCustomEvent(json) ◄──────── post(step|tick|confirm|warn|error|done|failed)
  progress / Cancel (wasCancelled on tick)    ─────────────► worker.cancel(): kill the git process tree
  confirm → messageBox → worker.answer(id)    ─────────────► waits ≤ 10 min, then No
  done/failed → summary, busy cleared
```

- **Threading rule** (Autodesk *Threading_UM*): the worker makes no Fusion API call. The worker's only Fusion contact is `fireCustomEvent`, which Autodesk documents as callable from other threads. The log's Fusion-palette handler ignores records from other threads.
- **Deadlocks:**
  - questions have a bounded wait;
  - cancel, shutdown and failed delivery all mean No;
  - the single-push guard is released in `finally`;
  - a worker whose last message can't be delivered no longer blocks later pushes.
- **Cancellation honesty:** `push_export` tracks its phase. On cancel, it asks GitHub (`ls-remote`) whether the branch tip is the export commit, and reports one of four outcomes:
  - nothing was pushed;
  - the export was published;
  - only the empty repository's first commit was pushed;
  - it couldn't tell.
- **Package isolation (R-25):**
  - every shipped module uses relative imports;
  - the entry point requires a package, which is the explicit execution-mode boundary;
  - on load, the entry point forgets its own package's earlier modules, both in `sys.modules` and as package attributes, along with bare-named modules an older version loaded from the same folder;
  - modules from any other folder are left alone; a same-named package from another folder is refused;
  - `push_cli.py`, `diagnostic.py` and `fusion_git_core.py` stay standalone-capable.

## 3. Implementation (commits on the branch)

| Area | Main files |
|---|---|
| Cancellable git, R-21 hooks, Git discovery, history notes | `fusion_git_core.py` |
| Background worker and custom-event bridge | `push_worker.py`, `fusion_bridge.py`, `push_dialog.py` |
| Lifecycle, duplicate guard, R-25 purge | `Push_To_GitHub.py` |
| Export integrity | `fusion_export.py`, `export_checks.py`, `portable_names.py` |
| Synced-folder note | `dialog_helpers.py` |
| Token hardening (https only, no askpass or submodules, proxy/TLS refusal) | `fusion_git_core.py`, `push_controller.py` |
| Stricter Fusion stand-ins | `tests/fakes/adsk/core.py`, `fusion.py`, README (26 documented assumptions) |
| Package validation (no bare sibling imports) | `scripts/package.py` |
| CI: release tags for the update tests | `.github/workflows/ci.yml` |

**Behaviour changes users will notice:**
- the dialog closes when the push starts, and the result arrives as a message;
- questions that can be asked up front are asked before the push;
- every chosen format must export, or nothing is pushed;
- hooks don't run for token pushes, and a token push is refused if the repository's own config sets a proxy or TLS trust;
- a second installed copy warns instead of adding a button.

## 4. Tests

- **Counts:** 219 unit tests (3 skipped), up from 118; 35/35 integration tests. Both pass under `tests/hostile.gitconfig`, and the temp-folder guard finds nothing left behind.
- **Asynchrony:** real threads, with a simulated message loop. The stand-in queues custom events and never delivers them inside `fireCustomEvent`; UI calls from other threads are refused and fail the test. Tests cover:
  - ordering;
  - the confirm round trip;
  - timeout;
  - cancel before and after GitHub accepted the push, using real git hooks;
  - shutdown;
  - lost results;
  - a message box that lets the push finish while it's open.
- **Isolation (fresh interpreters):** stale bare names; update and rollback, checking all 26 module references; two versions; a same-named package; restarts; odd `sys.modules` entries; standalone execution. Also the real 0.3.3 and 0.4.0 tags:
  - the reported failure is reproduced as a control;
  - the 0.3.3 ↔ 0.6 ↔ 0.4.0 chain works.
- **Exports:** every failure kind (raise, False, empty, missing, corrupt), linked components, mm/warning, per-body naming with nested components and duplicate names, Unicode and reserved names, and old profiles.
- **Assertion lint** (stricter): constant assertions, calls on mock objects and helpers like `failed_text` no longer count as assertions.

## 5. Coverage (local, Windows; both suites)

| Module | Measured | Minimum |
|---|---|---|
| push_worker.py | 90.9% | 90 (new) |
| fusion_bridge.py | 84.7% | 81 (new) |
| portable_names.py | 100% | 90 (new) |
| export_checks.py | ~92% | 90 (new) |
| fusion_export.py | ~86.5% | 85 (was 68) |
| Push_To_GitHub.py | ~64.5% | 60 (was 50) |
| dialog_helpers.py | 82.0% | 80 (was 78) |
| fusion_git_core.py | ~88% | 85 |
| push_controller.py | ~91% | 90 |
| add-in layer group | 78.6% | 74 |
| credentials.py | 56.9% locally | 90; its real-vault tests run only in CI |

No minimum was lowered. The subprocess isolation scenarios aren't counted in coverage.

## 6. Security

- **R-21: three routes found, all reproduced with a fake token and fake hosts, all closed and tested:**
  1. **A `pre-push` hook.** Closed: `core.hooksPath` is an empty folder, and a token can't reach git without it.
  2. **`url.*.insteadOf = ext::<cmd>` plus `protocol.ext.allow`.** Closed: `GIT_ALLOW_PROTOCOL=https`, no askpass program, no submodule recursion.
  3. **Repository-local proxy plus `http.sslVerify=false`** (found by the security review). The token reached a TLS-terminating proxy, and URL-specific keys beat `-c` overrides. Closed: a token push is refused while the repository's own config, including its includes, sets a proxy or TLS trust. This is checked on the main thread and again in the push.
- **Also fixed from the review:**
  - design and component names are one line in commits and HISTORY.md;
  - invisible bidi and zero-width characters are removed from names;
  - an odd `sys.modules` entry no longer stops the add-in loading.
- **Open (not accepted):**
  - other non-routing repository settings, such as `http.extraHeader`;
  - a forged custom event from another in-process add-in. It would need code execution already, so it isn't an escalation.
- **Unchanged:** R-08, R-10, R-12 and R-14 remain "acceptance proposed", awaiting the maintainer.

## 7. Export validation: what is and isn't proven

- **Basic validation (automated):** before Git starts, each requested format must:
  - exist and be non-empty;
  - have the right signature (a ZIP for F3D, `ISO-10303-21` for STEP, a complete binary or ASCII STL, an IGES start record);
  - be under 100 MB;
  - not collide with another file case-insensitively.
- **Not proven:** that a file opens in CAD software, or that an F3D restores a design with linked components. That's CAD recoverability, covered by the manual re-import check in checklist J.
- **F3Z:** there is no documented API, so it isn't used. The linked-components warning and the history note are the mitigation. The residual (R-06) needs a maintainer decision after the live check.

## 8. Risk register changes

| Risk | Change |
|---|---|
| R-04 | Mitigated: background thread; live responsiveness check pending |
| R-06 | High → Medium; mitigated (detected, confirmed, recorded); residual not accepted |
| R-15 | Mitigated: duplicate guard; limits recorded |
| R-18 | 25 → 26 documented stand-in assumptions; checklist I–K target them |
| R-21 | Three routes; mitigated; residual open, not accepted |
| R-25 (new) | Same-process updates, reported and reproduced by DiegoV71; mitigated; live check K pending |
| R-26 (new) | Partial exports pushed as complete; mitigated (all or nothing) |

## 9. Manual (live Fusion) verification required: none has been done

These sections of `tests/MANUAL_CHECKLIST.md` are new or changed:

- **I. Background push:**
  - responsiveness;
  - Cancel before and after GitHub accepts;
  - a second push is refused;
  - questions on top;
  - closing the document mid-push;
  - Stop during a push.
- **J. Exports:**
  - linked-component question, note, and **re-import of the .f3d** (decides whether the R-06 warning is justified);
  - a 10 mm cube from an inch design comes out at 10 mm;
  - per-body files and their positions;
  - hidden bodies;
  - a failed export pushes nothing;
  - unsafe names.
- **K. Updates:**
  - Stop → replace files → Run;
  - Community Store update;
  - rollback;
  - five restarts;
  - Run on Startup after an update;
  - duplicate copy;
  - other add-ins unaffected;
  - DiegoV71's macOS Store retest, if available.
- **L.** Synced-folder note.
- **M.** macOS items (Experimental).
- **H.** New stand-in assumptions:
  - custom events from the worker arrive;
  - `wasCancelled` after hide/show;
  - modal message boxes on top;
  - duplicate warning at startup;
  - linked detection, including broken links.

Key Fusion assumptions only a live run can confirm:
- the add-in folder is loaded as a package and Run re-executes the main file (if not, the add-in refuses to start; K finds out);
- `STLExportOptions.unitType`;
- body proxies export at their assembly position;
- `isReferencedComponent` behaviour for nested and broken links;
- `fireCustomEvent` from a thread;
- whether modal message boxes deliver events while open (now handled either way).

## 10. Release readiness

| Gate | State |
|---|---|
| Automated tests, coverage, lint, docs, package, release check | Pass locally and in CI: Release workflow dry run 46062682150 passed all 14 jobs (Windows/Ubuntu/macOS tests, unusual Git config, coverage with real Credential Manager tests, package build); no release created |
| Independent reviews (correctness, security, test quality) | Done; every high and medium finding fixed with tests |
| Live Fusion checklist (Windows) | **Not run.** It blocks release |
| macOS | Experimental; CI only. **No claim of Fusion compatibility** |
| PR #20 merged | **No.** It blocks merging #21 |

**Order to release:**
1. Run the checklist on 0.5.0 (S3) and merge #20, then publish 0.5.0 per CONTRIBUTING.
2. Rebase or retarget #21 onto main and let CI run on the PR.
3. Run the full checklist, including I–M, on the 0.6.0 build.
4. Get the maintainer's decisions on the R-06 and R-21 residuals and the pending acceptances.
5. Date the CHANGELOG, tag and publish.
6. Ask DiegoV71 to retest the Store update.

Alternative: skip publishing 0.5.0 and ship S3 and S4 together as 0.6.0, after one checklist run. That's a maintainer decision.

## 11. Recommendations for S5

1. **Single-history default (Q1).**
   - Seed design-folder allocation from the repository's tree on GitHub, which resolves R-24.
   - Handle files a profile no longer exports. For example, switching to per-body STL leaves the old `Bracket.stl` behind.
2. **Onboarding and dialog redesign.** The dialog now closes on push, so add a small "last push" status, or reopen the dialog on failure.
3. **Setup check.**
   - The minimum Git version.
   - Detect a repository whose own proxy/TLS settings will block token pushes before the first push.
   - Explain the folder-in-OneDrive note.
4. **Icon (S5, parallel).** Use `Assets/Branding/Icon-Master.png`, which is untouched here.
5. **Tests.** Shorten the 60 s push timeout and the 30 s hook sleeps (slow failures). Measure coverage inside the subprocess scenarios.
6. **Decide the "acceptance proposed" risks:** R-08, R-10, R-12, R-14, and the R-06 and R-21 residuals.

---

## 12. Addendum: maintainer decisions and the R-21 follow-up (2026-11-27)

**Decisions**
- No standalone 0.5.0: S3 and S4 ship together as 0.6.0. The CHANGELOG sections are merged.
- **Accepted** with their documented mitigations: R-08, R-10, R-12, R-14.
- **R-06** is accepted **conditionally**: for distribution before 1.0 only, and only while the incomplete recoverability is communicated. That communication is the pre-push question, the `HISTORY.md` note, the README "known limitation" and the CHANGELOG. The live restore check (checklist step 6, J2) stays a requirement for 1.0.
- **R-21 is not accepted.** It was investigated further (below).
- PR #20 is merged first, then #21 against main; the candidate is prepared for manual verification. It is published only after the maintainer confirms the checklist.

**R-21 follow-up.** The investigation used `workpapers/r21_probe.py`: a synthetic token, local HTTPS servers with a throwaway certificate, and no system or global Git config.

| # | Route | Before | After |
|---|---|---|---|
| E1 | `GIT_TRACE_CURL` / `GIT_CURL_VERBOSE` in the user's environment with `GIT_TRACE_REDACT=0` | Base64 token in the trace file, in stderr and in the add-in's error message | Fixed: redaction forced, HTTP traces off for token commands, base64 form redacted |
| E2 | Redirect to another host | Token not sent | No change needed |
| E3 | `remote.origin.pushurl` / `url.*.insteadOf` to another repository on the same host | Token and design sent there | Fixed: a token push is refused unless every address Git will use is the saved repository |
| E4 | Same-user process reading the `git` process environment | Token readable | Open. It needs the same rights as reading the stored token from Windows Credential Manager. 1.0 proposal: no token in the environment (a one-time local channel or a short-lived private file), plus an OS store with per-application access control |

**Manual checklist.** The S3 and S4 requirements are consolidated into one ordered session (`tests/MANUAL_CHECKLIST.md`). All 73 earlier criteria are kept, with IDs A1–M3. Two live checks of the R-21 refusals (R1, R2) are new.
