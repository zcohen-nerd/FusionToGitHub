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

*Last reviewed: 2026-11-27, sprint S3 (target release 0.5.0).*

## Summary

| ID | Risk | Residual L×I | Status | Next step |
|----|------|-------------|--------|-----------|
| R-01 | Remote work overwritten by force push | 1×5 = 5 Low | **Resolved** (0.3.3, 0.4.0) | — |
| R-02 | Local uncommitted work misplaced by the push | 1×3 = 3 Low | **Resolved** (0.4.0) | — |
| R-03 | Private local commits published | 1×4 = 4 Low | **Resolved** (0.4.0) | — |
| R-04 | Fusion freezes during Git network work | 3×3 = 9 Medium | Mitigated | S4 background thread |
| R-05 | Broken or empty public release | 1×2 = 2 Low | **Resolved** (0.3.3) | — |
| R-06 | Backups of designs with linked components can't be restored | 3×5 = 15 High | Open | S4 (F3Z or warning) |
| R-07 | Token exposed through helpers, URLs or logs | 1×3 = 3 Low | **Resolved** (0.4.0, 0.5.0) | — |
| R-08 | Proprietary design pushed to a public repository | 2×5 = 10 Medium | Acceptance proposed | Maintainer decision |
| R-09 | macOS users can't find Git or sign in | 2×2 = 4 Low | Mitigated (labelled Experimental) | S4 small fixes |
| R-10 | GitHub size limits exceeded | 2×2 = 4 Low | Acceptance proposed | Maintainer decision; LFS after 1.0 |
| R-11 | Autodesk App Store rejection | 2×2 = 4 Low | Open (separate track after 1.0) | Questions to Autodesk |
| R-12 | Single maintainer's capacity | 3×2 = 6 Low | Acceptance proposed | Maintainer decision |
| R-13 | Fusion API changes break the add-in | 2×3 = 6 Low | Mitigated | Manual check every release |
| R-14 | Git is an external dependency | 3×1 = 3 Low | Acceptance proposed | Maintainer decision |
| R-15 | Two copies installed after an upgrade | 2×2 = 4 Low | Mitigated (docs) | S4 duplicate guard |
| R-16 | Supply-chain compromise of a release | 1×3 = 3 Low | **Resolved** (0.3.3) | Keep actions pinned |
| R-17 | Contributor attribution | 1×1 = 1 Low | **Resolved** (0.3.3) | — |
| R-18 | Fusion test doubles diverge from real Fusion | 3×3 = 9 Medium | Open (new in S3) | Manual checklist every release |
| R-19 | Settings migration loses saved repositories | 1×3 = 3 Low | Mitigated (new in S3) | Confirm on a real 0.4.0 settings file |
| R-20 | Per-design folders surprise existing users | 3×2 = 6 Low | Open (new in S3) | Release notes; S5 docs |
| R-21 | A repository's pre-push hook can read the stored token | 1×4 = 4 Low | Acceptance proposed | Maintainer decision |
| R-22 | Masked token field unsupported in some Fusion builds | 2×3 = 6 Low | Open (new in S3) | Manual check of the Token field |
| R-23 | Stored token sent to a server it wasn't stored for | 1×4 = 4 Low | **Resolved** (0.5.0) | — |
| R-24 | Two saved repositories for one GitHub repository allocate design folders independently | 2×2 = 4 Low | Open (new in S3) | Seed folder names from the repository's tree (S5) |

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
- **Resolved when:** S4 runs the network phase on a worker thread and the live test shows Fusion stays responsive during a slow push and during sign-in.

### R-06 — Unrestorable backups of designs with linked components — Open (High)
- **Cause:** the add-in always exports `.f3d`; for designs with external references Fusion may need `.f3z` (audit BUG-02, unverified live).
- **Impact:** a backup that looks fine but can't be opened.
- **Resolved when:** S4 exports F3Z when external references exist, or shows a clear warning, verified by re-importing a linked assembly in Fusion. If Fusion's API can't export F3Z, the residual needs maintainer acceptance.

### R-08 — Proprietary design pushed to a public repository — Acceptance proposed
- **Cause:** the user chooses the repository; the add-in makes no GitHub API calls, so it can't see visibility.
- **Mitigation:** README warning in setup; a one-time notice per repository before the first push; PRIVACY.md.
- **Why acceptance is proposed:** the risk is inherent to publishing to a user-chosen repository. Detecting visibility would need API access and a token with broader scope, which conflicts with the least-privilege design.
- **Needs:** maintainer acceptance.

### R-10 — GitHub size limits exceeded — Acceptance proposed
- **Mitigation:** exports of 100 MB or more are refused before anything is pushed; over 50 MB needs confirmation; README "Size limits".
- **Why acceptance is proposed:** Git LFS is deferred until after 1.0 (decision Q15). Repository growth over many versions is inherent to keeping every version.
- **Needs:** maintainer acceptance.

### R-12 — Single maintainer's capacity — Acceptance proposed
- **Mitigation:** CI gates, a release checklist, a sprint plan, contributor docs.
- **Needs:** maintainer acceptance (support is best effort, as SECURITY.md states).

### R-13 — Fusion API changes — Mitigated
- **Mitigation:** the manual Fusion checklist runs before each release, with the Fusion build recorded; API calls with version differences already have fallbacks (format table, LogLevels).

### R-14 — Git is an external dependency — Acceptance proposed
- **Why acceptance is proposed:** bundling Git would make the add-in far larger and leave security updates to this project. "Git not found" is explained in the dialog; S5's setup check will state the minimum version.
- **Needs:** maintainer acceptance.

### R-15 — Two copies installed after an upgrade — Mitigated
- **Mitigation:** upgrade instructions say to remove the old folder first.
- **Resolved when:** S4 adds a startup guard that warns instead of registering a second command.

### R-18 — Fusion test doubles diverge from real Fusion — Open (new in S3)
- **Cause:** the dialog tests run against simplified stand-ins for Fusion's API (`tests/fakes/adsk`). They prove the add-in's logic, not Fusion's behaviour.
- **Mitigation:** the stand-ins are kept small and document their assumptions; every release runs the manual Fusion checklist (`tests/MANUAL_CHECKLIST.md`), which targets those assumptions.
- **Resolved when:** never fully; this is managed, not removed. Review if a release finds a mismatch.

### R-19 — Settings migration loses saved repositories — Mitigated (new in S3)
- **Mitigation:** the pre-0.5.0 file is copied once to `.fusion_git_repos.json.v0-backup` before its first rewrite; unreadable files are preserved; invalid entries are kept; saves are atomic. Covered by unit tests.
- **Resolved when:** a real settings file from 0.4.0 has been upgraded in Fusion without loss.

### R-20 — Per-design folders surprise existing users — Open (new in S3)
- **Cause:** decision Q11 puts each design's exports and its `HISTORY.md` in a folder named after the design. Users upgrading from 0.4.0 will see new pushes land in `<design>/` instead of the repository root; the old `CHANGELOG.md` stays where it was and is referenced from each new history file.
- **Mitigation:** CHANGELOG and release notes explain the change.
- **Resolved when:** S5's documentation and success dialog show where files go.

### R-21 — A pre-push hook can read the stored token — Acceptance proposed
- **Cause:** the token is passed to `git push` in its environment; a repository's own `pre-push` hook runs inside that process.
- **Mitigation:** documented in SECURITY.md; only repositories the user controls are expected.
- **Needs:** maintainer acceptance, or a later change to `--no-verify` for token pushes (which would skip hooks users rely on).

### R-23 — Stored token sent to a server it wasn't stored for — Resolved (0.5.0)
- **Found by:** the S3 independent security review. Tokens were stored per repository name; pointing a saved repository at a clone on another server, or re-adding a removed repository's name, could have reused the token there.
- **Mitigation:** the server is stored with the token (Credential Manager comment field) and checked against the folder's actual push address, including the port, before every push; changing a repository's folder or server turns off Use Stored Token. Tokens from before 0.5.0 are bound on first use.
- **Resolution evidence:** `ReviewFixTests` in `tests/unit/test_push_controller.py`.

### R-24 — Design folders allocated independently by two saved repositories — Open (new in S3)
- **Cause:** the design-to-folder map lives in each saved repository's settings. Two saved entries pointing at the same GitHub repository (or two computers) could each give a different design the folder "Bracket".
- **Impact:** two designs' files and histories in one folder.
- **Resolved when:** folder allocation also checks the folders already in the repository on GitHub (planned with S5's single-history default).

### R-22 — Masked token field unsupported in some Fusion builds — Open (new in S3)
- **Cause:** `StringValueCommandInput.isPassword` is assumed to exist; if it doesn't, the add-in logs a warning and the token is visible while typed.
- **Resolved when:** the manual checklist confirms the field shows dots in the current Fusion build.
