# Risk register

The formal list of known risks to FusionToGitHub users and to the project
(maintainer decision Q17). It started from the v1.0 readiness audit
(2026-11-26) and is updated in every sprint and release.

**Rules**

- Every known risk is listed, with its severity, mitigation, and what would
  count as resolved.
- A risk is only **accepted** when the maintainer has explicitly agreed, and
  the rationale is recorded here. Until then it is **acceptance proposed**.
  New risks are never accepted silently.
- Likelihood (L) and impact (I) use a 1–5 scale. Severity = L × I
  (1–25): **High** ≥ 15, **Medium** 8–14, **Low** ≤ 7. Values are judgements,
  not measurements.
- Status: **Open** (work planned), **Mitigated** (reduced, residual remains),
  **Resolved** (resolution criteria met), **Accepted** (maintainer agreed),
  **Acceptance proposed**.

*Last reviewed: 2026-11-28, sprint S5 (development version 0.7.0, unpublished).*

## Summary

| ID | Risk | Residual L×I | Status | Next step |
|----|------|-------------|--------|-----------|
| R-01 | Remote work overwritten by force push | 1×5 = 5 Low | **Resolved** (0.3.3, 0.4.0) | — |
| R-02 | Local uncommitted work misplaced by the push | 1×3 = 3 Low | **Resolved** (0.4.0) | — |
| R-03 | Private local commits published | 1×4 = 4 Low | **Resolved** (0.4.0) | — |
| R-04 | Fusion freezes during Git network work | 1×3 = 3 Low | Mitigated (S4: background thread) | Live responsiveness check (checklist I) |
| R-05 | Broken or empty public release | 1×2 = 2 Low | **Resolved** (0.3.3) | — |
| R-06 | Backups of designs with linked components can't be restored | 2×4 = 8 Medium | **Accepted, conditionally** (before 1.0 only, while communicated) | Live restore check required for 1.0 |
| R-07 | Token exposed through helpers, URLs or logs | 1×3 = 3 Low | **Resolved** (0.4.0, 0.6.0) | — |
| R-08 | Proprietary design pushed to a public repository | 2×5 = 10 Medium | **Accepted** (2026-11-27) | Keep the mitigations |
| R-09 | macOS users can't find Git or sign in | 2×2 = 4 Low | Mitigated (labelled Experimental) | S4 small fixes |
| R-10 | GitHub size limits exceeded | 2×2 = 4 Low | **Accepted** (2026-11-27) | LFS after 1.0 |
| R-11 | Autodesk App Store rejection | 2×2 = 4 Low | Open (separate track after 1.0) | Questions to Autodesk |
| R-12 | Single maintainer's capacity | 3×2 = 6 Low | **Accepted** (2026-11-27) | — |
| R-13 | Fusion API changes break the add-in | 2×3 = 6 Low | Mitigated | Manual check every release |
| R-14 | Git is an external dependency | 3×1 = 3 Low | **Accepted** (2026-11-27) | — (S5: Check My Setup states the minimum version) |
| R-15 | Two copies installed after an upgrade | 2×1 = 2 Low | Mitigated (S4: warning, no second button) | Live duplicate check (checklist K) |
| R-16 | Supply-chain compromise of a release | 1×3 = 3 Low | **Resolved** (0.3.3) | Keep actions pinned |
| R-17 | Contributor attribution | 1×1 = 1 Low | **Resolved** (0.3.3) | — |
| R-18 | Fusion test doubles diverge from real Fusion | 3×3 = 9 Medium | Open (new in S3; 25 assumptions in S4) | Manual checklist every release |
| R-19 | Settings migration loses saved repositories | 1×3 = 3 Low | Mitigated (new in S3) | Confirm on a real 0.4.0 settings file |
| R-20 | Per-design folders surprise existing users | 2×2 = 4 Low | Mitigated (S5: the dialog and summary say where files go) | S6 docs |
| R-21 | A repository's own hooks or settings could expose the stored token | 1×4 = 4 Low | Mitigated, **not accepted** (maintainer, 2026-11-27) | Live push with a token; 1.0: token kept out of process environments |
| R-22 | Masked token field unsupported in some Fusion builds | 2×3 = 6 Low | Open (new in S3) | Manual check of the Token field |
| R-23 | Stored token sent to a server it wasn't stored for | 1×4 = 4 Low | **Resolved** (0.6.0) | — |
| R-24 | Two saved repositories for one GitHub repository allocate design folders independently | 1×2 = 2 Low | Mitigated (S5: folders checked against GitHub) | Live check U14 |
| R-25 | An update in a running Fusion loads the previous version's modules | 1×3 = 3 Low | Mitigated (S4, reported by DiegoV71) | Live stop → update → run and Store update (checklist K) |
| R-26 | A failed or partial export is pushed as if it were a complete backup | 2×4 = 8 Medium | Mitigated (S4: all or nothing) | Live failure check |
| R-27 | Backups added straight to a repository's main branch | 2×2 = 4 Low | Mitigated (new in S5) | Live checks U8, U9, U16 |

## Details

### R-01 — Remote work overwritten by force push — Resolved
- **Was:** a saved "Force Push" option and a lease refreshed by the add-in's own pull could overwrite colleagues' commits (audit REL-01, reproduced).
- **Mitigation:** force push removed (0.3.3); exports built on GitHub's tip and pushed fast-forward only, rebuilt if GitHub moved (0.4.0).
- **Resolution evidence:** T_NOFORCE (no force option in source), T_PIPE_09 (overwrite scenarios, fails on the old code).

### R-02 — Local uncommitted work misplaced — Resolved
- **Was:** auto-stash identified by a fixed message; stash could be stranded, or the wrong one restored (REL-02/03/04/14).
- **Mitigation:** since 0.4.0 the add-in never touches the local working tree, index, stash or branches.
- **Resolution evidence:** every pipeline test asserts invariant I1 with a fixture proven to detect each kind of change.

### R-03 — Private local commits published — Resolved
- **Was:** snapshot branches forked from the local HEAD (SEC-01).
- **Mitigation:** exports are built on GitHub's branch tip (0.4.0).
- **Resolution evidence:** T_PIPE_03 (an unpushed private commit is not published).

### R-04 — Fusion freezes during Git network work — Mitigated
- **Cause:** Git runs on Fusion's main thread.
- **Mitigation so far:** every Git call has a time limit (60 s local, 600 s network) and kills the whole process tree when reached; the progress dialog repaints between steps. S3 separates the push into a main-thread plan and a Git-only execute step (`push_controller`), the boundary the background thread will use.
- **S4:** after the export and every question that can be asked up front (publication notice, identity, linked components, large files), the Git work runs on a background thread (`push_worker.py`) that never calls Fusion. Progress, the remaining question (reusing a branch), warnings and the result reach Fusion's main thread only through a custom event (`fusion_bridge.py`), as Autodesk's threading guide prescribes. A question waits at most 10 minutes and counts as No on timeout, cancel or shutdown, so the worker can't deadlock. Cancel kills the Git process tree and reports truthfully whether GitHub had already accepted the push. One push runs at a time; `stop()` cancels a running push.
- **Evidence:** `tests/unit/test_push_worker.py`, `tests/unit/test_worker_bridge.py`, `tests/unit/test_core_cancel_hooks.py` (real threads; the stand-in queues custom events and refuses UI calls off the main thread).
- **Resolved when:** the live checklist (section I) shows Fusion stays responsive during a slow push and during sign-in, and Cancel behaves as tested. The export itself still runs on the main thread (Fusion requires it).

### R-06 — Unrestorable backups of designs with linked components — Accepted conditionally (before 1.0)
- **Cause:** the add-in exports `.f3d`; for designs with external references Fusion may need `.f3z` (audit BUG-02, unverified live).
- **Impact:** a backup that looks fine but can't be opened on its own.
- **Finding (S4):** Fusion's documented API has no `.f3z` export. `createFusionArchiveExportOptions` writes `.f3d`; the only route seen is the undocumented text command `data.fileExport f3z`, which has reported naming problems and isn't used.
- **Mitigation (S4):** linked components are detected (`Occurrence.isReferencedComponent` across all occurrences) when F3D is exported. The add-in names them and asks before pushing ("this backup might not restore on its own"); declining pushes nothing. Accepting records a note in the design's `HISTORY.md`, so the backup is never presented as complete.
- **Evidence:** `tests/unit/test_fusion_export.py`, `tests/unit/test_dialog_exports.py` (against simulated Fusion).
- **Residual:** a user who accepts still has an F3D that may not restore alone; the linked designs stay in Fusion's cloud.
- **Decision (accepted by the maintainer on 2026-11-27):** accepted for distribution **before 1.0 only**, and only while incomplete recoverability is communicated explicitly. That means:
  - the confirmation question before every such push;
  - the `HISTORY.md` note;
  - the README's "Linked components" limitation;
  - the CHANGELOG.

  If any of these is removed, the acceptance lapses.
- **Open requirement for 1.0:** a live restore check. A pushed `.f3d` with linked components is re-opened in Fusion and the result recorded (consolidated checklist, step 6). 1.0 can't ship until it is done and the warning text matches the result.

### R-08 — Proprietary design pushed to a public repository — Accepted
- **Cause:** the user chooses the repository; the add-in makes no GitHub API calls, so it can't see visibility.
- **Mitigation:** README warning in setup; a one-time notice per repository before the first push; PRIVACY.md.
- **Why accepted:** the risk is inherent to publishing to a user-chosen repository. Detecting visibility would need API access and a token with broader scope, which conflicts with the least-privilege design.
- **Decision:** accepted by the maintainer on 2026-11-27, with the mitigations above kept in place.

### R-10 — GitHub size limits exceeded — Accepted
- **Mitigation:** exports of 100 MB or more are refused before anything is pushed; over 50 MB needs confirmation; README "Size limits".
- **Why accepted:** Git LFS is deferred until after 1.0 (decision Q15). Repository growth over many versions is inherent to keeping every version.
- **Decision:** accepted by the maintainer on 2026-11-27, with the size checks kept in place.

### R-12 — Single maintainer's capacity — Accepted
- **Mitigation:** CI gates, a release checklist, a sprint plan, contributor docs.
- **Decision:** accepted by the maintainer on 2026-11-27; support is best effort, as SECURITY.md states.

### R-13 — Fusion API changes — Mitigated
- **Mitigation:** the manual Fusion checklist runs before each release, with the Fusion build recorded; API calls with version differences already have fallbacks (format table, LogLevels).

### R-14 — Git is an external dependency — Accepted
- **Why accepted:** bundling Git would make the add-in far larger and leave security updates to this project. "Git not found" is explained in the dialog.
- **S5:** Check My Setup reports the Git version found and where, warns below 2.30 (the oldest version the add-in is meant for; older ones aren't tested), and reports a missing Git with a download link as soon as a new user opens the dialog.
- **Decision:** accepted by the maintainer on 2026-11-27.

### R-15 — Two copies installed after an upgrade — Mitigated
- **Mitigation:** upgrade instructions say to remove the old folder first. Since S4, a copy that finds another running copy of any version (an entry module with the same command id, outside its own folder) warns once and adds no button, event or handler; its `stop()` leaves the other copy alone. The check only reads other modules' attributes and changes nothing. Limits: a copy that crashed without stopping still counts as running until Fusion restarts (a false warning, no harm). If a pre-0.6.0 copy started after this one took over, that copy's own `stop()` can remove this copy's button, because older versions don't have the guard.
- **Evidence:** `tests/unit/test_addin_lifecycle.py`, `two_versions` in `tests/unit/test_package_isolation.py`.
- **Resolved when:** the live duplicate check (checklist K) passes.

### R-18 — Fusion test doubles diverge from real Fusion — Open (new in S3)
- **Cause:** the dialog tests run against simplified stand-ins for Fusion's API (`tests/fakes/adsk`). They prove the add-in's logic, not Fusion's behaviour.
- **Mitigation:** the stand-ins are kept small and document their assumptions; every release runs the manual Fusion checklist (`tests/MANUAL_CHECKLIST.md`), which targets those assumptions.
- **S4:** the stand-ins became stricter: handlers are held weakly as in Fusion, UI calls from other threads fail, and custom events are queued and delivered only by a simulated message loop. They now also simulate assemblies and exports, so there are 25 documented assumptions (`tests/fakes/README.md`); checklist sections I–K target the new ones.
- **Resolved when:** never fully; this is managed, not removed. Review if a release finds a mismatch.

### R-19 — Settings migration loses saved repositories — Mitigated (new in S3)
- **Mitigation:** the pre-0.5.0 file is copied once to `.fusion_git_repos.json.v0-backup` before its first rewrite; unreadable files are preserved; invalid entries are kept; saves are atomic. Covered by unit tests.
- **Resolved when:** a real settings file from 0.4.0 has been upgraded in Fusion without loss.

### R-20 — Per-design folders surprise existing users — Open (new in S3)
- **Cause:** decision Q11 puts each design's exports and its `HISTORY.md` in a folder named after the design. Users upgrading from 0.4.0 will see new pushes land in `<design>/` instead of the repository root; the old `CHANGELOG.md` stays where it was and is referenced from each new history file.
- **Mitigation:** CHANGELOG and release notes explain the change. Since S5 the dialog's "Saves to" line shows the branch and folder before a backup, and the summary after it shows where it went, with a link to the folder on GitHub.
- **Resolved when:** S6's user documentation describes the layout.

### R-21 — A repository's own hooks or settings could expose the stored token — Mitigated (S4)
- **Cause:** the token is passed to the network `git` process in its environment, and that process obeys the repository's own `.git/config`. Three routes were found and reproduced with a fake token and fake hosts:
  - a `pre-push` hook (it inherits the environment);
  - a program named in repository config: `url.<x>.insteadOf = ext::<command>` plus `protocol.ext.allow=always` ran that command during `ls-remote` and `push`, with the token visible (found in S4);
  - routing through someone else's proxy: `http.proxy` plus `http.sslVerify=false` sent the token, inside the `Authorization` header, to a TLS-terminating proxy. URL-specific forms (`http.https://github.com/.proxy`) beat any `-c` override on the command line. This needs no program at all (found by the S4 security review).
- **Mitigation (S4):** for every Git command that carries the token:
  - `core.hooksPath` points at an empty temporary folder, so no hook runs; a token can't be passed to Git without that folder;
  - `GIT_ALLOW_PROTOCOL=https` overrides every `protocol.*.allow` setting, so `ext::`, `file`, `ssh` and remote helpers can't run;
  - inherited `GIT_ASKPASS` and `SSH_ASKPASS` are removed and `core.askPass` is empty;
  - submodule recursion is off for fetch and push; the credential helper list is reset and the token is offered to one host only (R-07, R-23);
  - the push is **refused**, before anything is sent, while the repository's own config (with its includes) sets a proxy (`http.*proxy*`, `remote.*.proxy`) or TLS trust (`http.*sslVerify`, `sslCAInfo`, `sslCAPath`, `sslBackend`, client certificates, `curloptResolve`). It is checked in the dialog (dialog stays open, with an explanation) and again in the push. Global settings, such as a company proxy, are not affected.
- **Behaviour changes:** a repository's `pre-push` hook no longer runs when the add-in pushes with a stored token (pushes through Git Credential Manager, which carry no token, are unchanged). A repository with its own proxy or TLS settings can't be used with a stored token until they're moved to the global config. Documented in SECURITY.md.
- **Evidence:** `HookIsolationTests` in `tests/unit/test_core_cancel_hooks.py`: the hook and `ext::` reproductions, each with a control run that shows the attack works without the mitigation, plus the detection of proxy and TLS settings (including through `include.path`) and the refusal.
- **Decision (maintainer, 2026-11-27): not accepted.** The remaining exposure was investigated further.
- **Investigation (S4, after the decision):** `docs/audit/workpapers/r21_probe.py`. It used a synthetic token, local HTTPS servers on 127.0.0.1 with a throwaway certificate, and no system or global Git config.

  | # | Route | Result before | Now |
  |---|---|---|---|
  | E1 | Tracing in the user's environment (`GIT_TRACE_CURL` / `GIT_CURL_VERBOSE` with `GIT_TRACE_REDACT=0`) | The `Authorization` header, with the token in base64, was written to the trace file, to stderr, and from there into the add-in's error message, whose redaction knew only the raw token | **Fixed.** Token-carrying commands force `GIT_TRACE_REDACT=1` and drop the HTTP trace variables; redaction also covers the base64 `user:token` form |
  | E2 | Redirect to another host (`http.followRedirects=true`) | The other host received no token | Safe; no change needed |
  | E3 | Another repository on the **same** host (`remote.origin.pushurl`, `url.*.insteadOf` / `pushInsteadOf`) | The token, and the design, went to an attacker-chosen repository; the host check passed | **Fixed.** A token push is refused unless the fetch, push and configured addresses are all the same repository and match the GitHub address saved for it. Checked in the dialog and again in the push |
  | E4 | Another program running as the same user reads the environment of a running `git` process | The token is readable | **Open**, see below |

- **Remaining exposure (open, not accepted):**
  - **E4.** During a push, the token sits in the environment of the `git` processes. Another program running as the same Windows user can read it there, with the same rights it needs to read the stored token directly from Windows Credential Manager (`CredRead`, no prompt). So it adds no new reader. On macOS, stored tokens aren't supported. **Proposed for 1.0:** stop passing the token in the environment. Hand it to the credential helper through a one-time local channel (a single-use loopback answer bound to a random nonce), or through a short-lived file that only the user can read. Then pair that with an OS store that has per-application access control, so the stored token itself is protected too.
  - Other repository settings that neither run a program nor redirect the connection (for example `http.extraHeader` or cookie files) are not refused, because none of them can send the token elsewhere.
  - Anything that can write a repository's `.git` folder can usually also run code as the user some other way.

  Review again whenever a Git command that carries the token is added.

### R-23 — Stored token sent to a server it wasn't stored for — Resolved (0.6.0)
- **Found by:** the S3 independent security review. Tokens were stored per repository name; pointing a saved repository at a clone on another server, or re-adding a removed repository's name, could have reused the token there.
- **Mitigation:** the server is stored with the token (Credential Manager comment field) and checked against the folder's actual push address, including the port, before every push; changing a repository's folder or server turns off Use Stored Token. Tokens from before 0.5.0 are bound on first use.
- **Resolution evidence:** `ReviewFixTests` in `tests/unit/test_push_controller.py`.

### R-24 — Design folders allocated independently by two saved repositories — Mitigated (S5)
- **Cause:** the design-to-folder map lives in each saved repository's settings. Two saved entries pointing at the same GitHub repository (or two computers) could each give a different design the folder "Bracket".
- **Impact:** two designs' files and histories in one folder.
- **Mitigation (S5):** each design's `HISTORY.md` carries a hidden marker with a hash of the design's Fusion id. Before building a commit, the push reads the markers of the design folders on the branch it builds on. A folder whose history belongs to another design is never used; the backup goes to the next free "<name> (n)". A design whose marked folder already exists under another name goes there. The settings then remember the folder. The marker is a 16-character SHA-256 prefix, so the Fusion id itself isn't published (PRIVACY.md).
- **Hardening from the S5 reviews:** the marker only counts on its own line right after the title, so marker text inside a design name or a note can't claim a folder. Folder names are read without Git's quoting, so non-ASCII names are checked too. A folder that differs only in letter case counts as the same folder (Windows and macOS can't hold both). A design that was never saved (a provisional, name-based id) doesn't mark its folder, so once saved it keeps that folder instead of moving. What a repository can make a push read is bounded: HISTORY.md files over 1 MB aren't opened, and at most 300 design folders are examined.
- **Limits:** a history written before 0.7.0, or by a never-saved design, has no marker, so it can't be told apart and is kept by whichever design uses it next (and marked). Two pushes racing on the same branch can still both pick a free name; the second is rejected as non-fast-forward and rebuilt on the first, which re-runs the check. A "Design folders go in" template that puts the design's name inside a longer folder name (for example `{filename}-{timestamp}`) gets no check. Anyone with write access to the repository can add a folder carrying another design's marker; such a person could change the repository in any way anyway. The marker is the same in every repository a design is backed up to, so it shows that two backups are of the same design (without saying which).
- **Evidence:** `tests/unit/test_core_design_folders.py` (real Git), `DesignFolderOwnershipTests` in `tests/unit/test_dialog_ux.py`.
- **Resolved when:** live check U14 passes.

### R-25 — An update in a running Fusion loads the previous version's modules — Mitigated (S4)
- **Reported by:** DiegoV71 ([issue #11](https://github.com/zcohen-nerd/FusionToGitHub/issues/11)), with a reproduction. A Community Store update from 0.3.3 to 0.4.0 in the same Fusion process on macOS (Fusion 2706.1.17) didn't start 0.4.0, and the Store rolled back to 0.3.3. Outside Fusion, with 0.3.3's `fusion_git_core` and `dialog_helpers` already loaded under their bare names, importing 0.4.0 raises `ImportError: cannot import name 'push_export' from 'fusion_git_core'`.
- **Cause:** the add-in's modules import each other by bare name (`import fusion_git_core`) and the add-in folder is put on `sys.path`. Python reuses a module already loaded under that name, from the old version or from another add-in with a module of the same name.
- **Impact:** an update, downgrade or restart in the same Fusion session fails to start (or runs mixed code) until Fusion is restarted. The Store's rollback limits the damage; Community Store 1.1.0 also unloads a stopped add-in's modules, but the add-in must not rely on that.
- **Mitigation (S4, ships in 0.6.0; 0.4.0 is not republished):**
  - every shipped module imports its siblings relatively, and nothing is put on `sys.path`;
  - the entry point refuses to load outside a package; `push_cli.py` and `diagnostic.py` remain standalone scripts;
  - on load, the entry point forgets its own package's earlier modules and bare-named modules an older version loaded *from the same folder*, never anything else;
  - a same-named package from another folder is refused instead of mixed;
  - `scripts/package.py` rejects a bare sibling import in the ZIP.
- **Evidence:** `tests/unit/test_package_isolation.py`, run in fresh isolated interpreters. It reproduces the reported failure with the real 0.3.3 and 0.4.0 files as a control, then shows 0.3.3 → 0.6.0 → 0.4.0 → 0.6.0 → 0.3.3 working in one process. It also covers stale bare names, two installed versions, an unrelated add-in's same-named module (untouched), repeated start/stop and standalone execution.
- **Assumption:** the tests emulate Fusion as its add-in template implies: the folder is loaded as a package, and Run re-executes the main file. Autodesk doesn't document this. If Fusion instead loaded the main file as a plain top-level module, the add-in would refuse to start (by design, with a message). Checklist K finds out either way, and it must pass before release.
- **Found in review (fixed):** forgetting a module in `sys.modules` isn't enough, because `from . import x` reads the package's attribute `x` first. The old version's dialog, bridge and logging modules came back after an update. The purge now also detaches them from the package; the update and rollback scenarios check every module the add-in reaches (26 references).
- **Resolved when:** the live checks (checklist K: stop → update → run, Community Store update, rollback, restarts, Run on Startup) pass in Fusion, ideally including DiegoV71's macOS Store retest.

### R-27 — Backups added straight to a repository's main branch — Mitigated (new in S5)
- **Cause:** decision 1 makes one running history on the repository's default branch the default for new repositories (audit UX-01). Someone who shares a repository with other work may not want commits on `main`, and a protected `main` refuses them.
- **Impact:** unexpected commits on `main`, or a refused backup.
- **Mitigation:** the dialog shows "Saves to: <branch> › <folder>" before every backup. Advanced → Backup branch sends backups to a branch of their own, which is created on the first backup. A refusal because of branch protection is explained ("…that branch is protected") with that suggestion. Commits are fast-forward only and touch only the design's folder, so nothing else on `main` is ever changed. Repositories saved by earlier versions keep their snapshot branches.
- **Evidence:** `HistoryModeTests` in `tests/unit/test_dialog_ux.py`, `ErrorCatalogTests` in `tests/unit/test_ux_helpers.py`.
- **Resolved when:** live checks U8, U9 and U16 pass.

### R-26 — A failed or partial export pushed as a complete backup — Mitigated (S4)
- **Was:** an export that raised was logged and skipped, so a push could contain only some of the requested formats (or none), and a file Fusion wrote empty or truncated was pushed as is.
- **Mitigation (S4):** every requested export must succeed and pass basic file checks before Git starts: the file exists, isn't empty, has the expected signature (ZIP for F3D, `ISO-10303-21` for STEP, a complete STL, an IGES start record), is under 100 MB, and no two files would overwrite each other on Windows or macOS. Any failure stops the push: nothing is pushed and `HISTORY.md` isn't changed. These checks don't prove a file opens in CAD software.
- **Evidence:** `tests/unit/test_names_checks.py`, `tests/unit/test_fusion_export.py`, `tests/unit/test_dialog_exports.py`.
- **Resolved when:** the live failure check (checklist J) behaves as tested.

### R-22 — Masked token field unsupported in some Fusion builds — Open (new in S3)
- **Cause:** `StringValueCommandInput.isPassword` is assumed to exist; if it doesn't, the add-in logs a warning and the token is visible while typed.
- **Resolved when:** the manual checklist confirms the field shows dots in the current Fusion build.
