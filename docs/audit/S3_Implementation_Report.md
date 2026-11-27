# Sprint S3 — Testability and Application Architecture: Implementation Report

*FusionToGitHub · branch `feat/s3-testability` · PR #20 · target 0.5.0 (unreleased) · 2026-11-27*

## 1. Executive summary

S3 turned the add-in from a 2,361-line Fusion event handler into seven focused modules, four of which have no Fusion dependency. The dialog is now tested automatically against lightweight Fusion stand-ins, and coverage rose from **22% to 75%** (CI, statements plus branches). Before S3 the add-in layer had no coverage at all; it is now at 74.8%.

Settings writes are atomic, versioned, migrated, recoverable and never silently discarded. Saved repositories can be edited and removed safely, and the approved decisions Q11, Q13, Q14 and Q17 are implemented.

Three independent read-only reviews (correctness, security, test quality) found no high-severity issues. Every medium finding and most low ones are fixed, with regression tests, including one real security gap: a stored token is now bound to the server it was saved for.

All 13 required GitHub checks pass on PR #20.

**Readiness:** ready to merge. 0.5.0 should not be published until the manual Fusion checklist (`tests/MANUAL_CHECKLIST.md`) passes, because nothing was run in real Fusion.

## 2. Architecture before and after

**Before (0.4.0)**

| File | Lines | Contents |
|---|---|---|
| `Push_To_GitHub.py` | 2,361 | Logging, the Credential Manager ctypes code, settings load/save, export, toolbar, and the entire dialog as nested closures inside one `CommandCreated` handler (the execute handler alone was ~525 lines). 0% test coverage. |
| `fusion_git_core.py` | — | Git (isolated commits, since S1) |
| `dialog_helpers.py` | — | Pure helpers |

**After (0.5.0)**

| Module | Lines | Role | Fusion? | Coverage (CI) |
|---|---|---|---|---|
| `Push_To_GitHub.py` | 309 | Entry point: run/stop, toolbar, wiring | yes | 51% |
| `push_dialog.py` | ~1,190 | `PushDialog`: inputs, state, validation, events, Edit/Remove, token entry | yes, through stand-ins | 79% |
| `fusion_export.py` | 185 | Export service; design name and stable ID | yes | 69% |
| `addin_logging.py` | ~265 | Log, redacting formatter, private files, Clear Log | palette only | 66% |
| `push_controller.py` | ~420 | Push workflow (`plan` on the main thread, then `execute`, Git only); profile Edit/Remove; token server binding | no | 92% |
| `settings_store.py` | ~440 | Versioned, atomic settings; migration; recovery; design folders | no | 86% |
| `credentials.py` | ~210 | Credential store interface; Windows Credential Manager; in-memory store for tests | no | 92% |
| `fusion_git_core.py` | ~830 | Git transaction service (+ identity via env, per-design history) | no | 87% |
| `dialog_helpers.py` | 382 | Pure helpers | no | 80% |

The Q6 boundary is in place: `PushPlan` is plain data, and `execute()` makes no Fusion API calls itself. Its UI callbacks still open Fusion message boxes, so S4 must hand those back to the main thread.

## 3. Files and modules changed

Twelve commits on `feat/s3-testability`:

| Commit | Change |
|---|---|
| `ed58acd` | chore: remove the Copilot agent and prompt files (Q13) |
| `704756f` | feat(settings): `settings_store.py` plus 13 unit tests |
| `35b6a72` | refactor(credentials): `credentials.py` plus a contract test |
| `7806be1` | feat(git): identity via env (Q14) and per-design history files (Q11) |
| `d701ac6` | feat(controller): `push_controller.py` |
| `accb2b6` | refactor(addin): split the dialog into modules; Edit/Remove (forked agent) |
| `2069d64` | test(addin): Fusion stand-ins (`tests/fakes/adsk`), dialog and lifecycle tests (forked agent) |
| `42cbe90` | fix: the independent review findings |
| `64bcc8b` | ci: unusual Git config job, temp-folder guard, coverage gate |
| `74238ea` | docs: 0.5.0, risk register, manual checklist, CONTRIBUTING, README |
| (last) | ci(coverage): raise the `credentials.py` minimum to 90% |

New files:
- **Source:** `src/{push_dialog,fusion_export,addin_logging,push_controller,settings_store,credentials}.py`
- **Test stand-ins:** `tests/fakes/adsk/*`
- **Unit tests:** `tests/unit/*`, plus `tests/hostile.gitconfig`
- **Scripts:** `scripts/coverage_gate.py`, `scripts/tempdir_guard.py`
- **Docs:** `docs/RISK_REGISTER.md`, `tests/MANUAL_CHECKLIST.md`

Removed: `.github/agents/*`, `.github/prompts/*`.

## 4. Approved decisions implemented

| Decision | Implementation |
|---|---|
| Q1 continuous history | `mode="single"` exists in core, controller and CLI (`historyMode` in the profile); the dialog default stays snapshot until S5. |
| Q6 background execution | `plan()` on the main thread, `execute()` Git only. Thread start and UI marshalling are S4. |
| Q7/Q8 | No Autodesk work in S3. |
| Q11 per-design `HISTORY.md` | Each design has a folder keyed by its cloud `dataFile.id`, so it is stable across renames. Collisions get "(2)". An unsaved design keeps its folder after its first save. `{timestamp}` folders don't split history. The legacy `CHANGELOG.md` is referenced from each new history file and never moved. |
| Q13 | Copilot files removed after confirming nothing references them. |
| Q14 repo-local identity | Saved in the profile and passed as `GIT_AUTHOR_*`/`GIT_COMMITTER_*` to `commit-tree` only. Global config only on an explicit "all repositories" answer; `.git/config` is never written. |
| Q15 / Q16 | No LFS. GitHub remains the supported host; the host logic (`server_of`) is generic. |
| Q17 risk register | `docs/RISK_REGISTER.md` with 24 risks. Six are "acceptance proposed" (R-08, R-10, R-12, R-14, R-21, plus R-06's residual if F3Z can't be exported), awaiting the maintainer's explicit acceptance. |

## 5. Tests and coverage

| | Before | After |
|---|---|---|
| Regression suite (`test_runner.py`) | 35 | 35 (updated guards; fixtures opt out of signing) |
| Unit tests (`tests/unit`) | 0 | 96 (settings 18, credentials 4, core identity/history 4, controller 25, dialog 36, lifecycle 9) |
| Overall coverage (CI) | 22% | 75% |
| Add-in layer | 0% | 74.8% |

The coverage gate enforces a minimum for every runtime module, set just below the measured value: core 85, controller 90, settings 85, credentials 90, dialog helpers 78, dialog 77, export 68, logging 65, entry point 50. The add-in layer as a whole must stay at 74% or above. Any new module without a minimum fails the gate.

Guards against meaningless coverage:
- each module has its own minimum, so a well-tested module can't hide an untested one;
- every unit test must assert something outside an `if`;
- the stand-ins fail a test on any unscripted question or unused scripted answer;
- deleted inputs raise when used;
- tests assert observable results: messages, the settings file, remote repository contents, credential store contents.

## 6. Security and data-integrity regression results

All S0–S2 guarantees still hold; all regression tests pass on Ubuntu, Windows and macOS, and again under `tests/hostile.gitconfig`.

| Area | Status |
|---|---|
| No force push | T_NOFORCE, T_PIPE_09 |
| Invariant I1 (local repository untouched) | Every pipeline test |
| No local commits published | T_PIPE_03 |
| Timeouts | T_PIPE_12 |
| Non-ASCII names | T_PIPE_14 |
| Size gate | T_PIPE_13 |
| Credential scoping (isolated from the user's Git config) | T_CORE_03 |
| URL secrets | T_CORE_05, T_PIPE_17 |
| Packaging | T_PACKAGE now also fails if a runtime module isn't packaged |
| Release gates | Unchanged |

Strengthened in S3 after review:
- the token is bound to its server (new risk R-23, now resolved);
- Edit/Remove are all-or-nothing;
- settings files are owner-only from creation on POSIX;
- tracebacks are redacted;
- profiles with a token in their address are hidden.

The leak guard found a real, long-standing problem: tests left Git's read-only object folders in the temp directory. It is fixed, and 1,210 old test folders were removed from the developer machine.

An incident during S2 led to a new rule: credential experiments must disable system and global Git config and use fake hosts. It is enforced in T_CORE_03 and written into CONTRIBUTING.

## 7. Known limitations and unresolved risks

- **Not run in real Fusion, and not on macOS hardware.** All dialog behaviour is verified against stand-ins (R-18). §H of the checklist lists the 13 Fusion behaviours they assume.
- Behaviour changes made during the refactor:
  - the design is exported before the publication notice and identity questions, so declining the notice wastes one export;
  - read-only (newer-version) settings refuse pushes;
  - token controls follow the credential store's availability rather than the OS check.
- **R-20:** existing users' new pushes go into per-design folders.
- **R-24:** two saved entries for one GitHub repository allocate design folders independently. Planned for S5.
- **R-21:** a repository's `pre-push` hook can read the stored token. Acceptance proposed.
- **Fidelity gaps in the stand-ins, not fixed:**
  - handler lifetime (the fake keeps handlers alive, so a garbage-collected handler can't fail a test);
  - `destroy`/`validateInputs` events are never fired;
  - value types aren't checked;
  - the progress dialog's cancel button isn't exercised.

  They are covered by the manual checklist.
- `Push_To_GitHub.py` still imports `adsk` at module level, so it can only be imported with the stand-ins (unchanged from before).

## 8. Manual Fusion verification required

`tests/MANUAL_CHECKLIST.md` takes about 20 minutes on Windows with a private test repository:
- A: install and upgrade from 0.4.0, including the settings `v0-backup`;
- B: new repository setup, including the blank name, a refused token URL, and identity;
- C: pushing, including per-design folders, renames and "(2)";
- D: the stored token, including the masked field;
- E: Edit and Remove;
- F: failures, including a corrupt settings file;
- G: logging and privacy;
- H: the 13 Fusion behaviours the stand-ins assume.

## 9. Release-readiness assessment

| Gate | Status |
|---|---|
| All existing regression tests pass | ✅ (CI, three operating systems, and under the unusual config) |
| New application and dialog tests pass | ✅ 96 |
| Coverage thresholds enforced by CI | ✅ |
| Settings corruption and migration handled safely | ✅ (unit- and dialog-tested) |
| Repository profiles editable and removable | ✅ (stand-in tested; manual check pending) |
| Data-safety and credential guarantees intact | ✅ |
| Packaging and docs accurate | ✅ (package has all nine runtime modules; check-docs passes) |
| Independent technical review complete | ✅ (three reviews; findings fixed) |
| Required GitHub checks pass | ✅ 13/13 |
| Manual Fusion checklist prepared | ✅ (execution pending) |
| **Publish 0.5.0** | ⏳ After the manual checklist passes in Fusion, per the release policy |

Recommendation: merge PR #20, run the checklist with main's CI test build, then release 0.5.0.

## 10. Recommended S4 approach

1. **Verify the stand-ins first.** Run checklist §H in live Fusion and correct any stand-in assumption that's wrong before building S4 on it.
2. **Background Git (Q6).**
   - Keep `plan()` (questions, export, settings) on the main thread.
   - Run `execute()` on a `threading.Thread`.
   - Marshal every UI interaction through a Fusion custom event (`app.registerCustomEvent` / `fireCustomEvent`):
     - progress steps become events;
     - `GitUI.confirm()` from the worker posts an event and waits on a `threading.Event` for the main thread's answer, which keeps `push_export` unchanged;
     - `warn`/`error` become events.
   - Wire the progress dialog's Cancel to a flag that ends the current Git process tree (the S1 kill path).
   - Collect the size and branch-reuse decisions before the thread starts where possible.
   - Test with the stand-ins (synchronous custom events) and a live "slow push / sign-in" check.
3. **Export correctness.**
   - F3Z, or a clear warning, for designs with linked components (R-06, High), verified by re-import.
   - STL in mm, with an optional one-file-per-body.
   - Names safe on every system.
   - Decide on partial export failures before committing.
4. **Install robustness:** a duplicate-install guard (R-15), toolbar dedupe on `CMD_ID`, and a synced-folder (OneDrive/Dropbox) warning.
5. **macOS (Experimental):** a list of Git locations to try, and accurate GCM guidance; Mac results are not release-blocking.
6. **Close the remaining stand-in fidelity gaps** as S4 touches the code: handler lifetime, destroy/validate events, cancel.
7. **Get maintainer sign-off** on the "acceptance proposed" risks.
