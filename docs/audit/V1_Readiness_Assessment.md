# v1.0 readiness assessment

**Candidate:** 0.9.0 — 1.0.0 release candidate 1, feature-complete, unpublished
**Date:** 2026-11-28
**Basis:** the v1.0 readiness audit (2026-11-26) and its Definition of Done (§R), the maintainer's decisions to date, the sprint reports S3–S7, and the independent pre-release reviews of S7.

## Verdict

**Feature-complete and automatically verified; not yet release-ready.**

Every engineering item the audit planned for 1.0 is implemented and covered by automated tests on Windows, macOS and Ubuntu. Two independent reviews in S7 (security, correctness) found no release-blocking problems, and every finding they raised has been fixed or documented. A third review (test quality) found no blockers either.

What stands between this candidate and 1.0 is evidence that only real Fusion, GitHub and people can provide:

1. **The live verification campaign** (102 mandatory criteria in the [acceptance matrix](../../tests/ACCEPTANCE_MATRIX.md)). None has been run yet.
2. **The linked-component restore check, J2**, which R-06's conditional acceptance requires before 1.0.
3. **The usability test** with at least three people new to Git (X1–X4).
4. A small number of **maintainer settings and decisions** (§5).

Nothing in this assessment, or in the code, has been verified in real Fusion. Simulated tests are never counted as live evidence.

## 1. Definition of Done (audit §R)

| Area | Item | State |
|---|---|---|
| Release integrity | Tag on main; CI on that SHA; version surfaces agree | Ready in the tooling (`check_release.py`, release workflow); applies at tagging |
| | Draft release with ZIP, `.sha256`, attestation; digest checked; human smoke test; immutable releases; tag ruleset | Draft, attestation and immutable releases in place; **tag ruleset missing** (maintainer); smoke test = live P1/P4 |
| | Byte-identical builds; commit SHA in the ZIP comment | Done with one toolchain: two builds with the same zlib are byte-identical. A build with a different zlib (this maintainer's Python uses zlib-ng) has identical files, names, timestamps and permissions but different compression, so the published ZIP is always CI's |
| | Validator rejects bad packages; exact contents; tools and tests absent | Done (now including `resources/`) |
| | No binaries tracked | Done (icons are small PNGs by design; no ZIPs) |
| Data integrity | I1 tree, index, stash, HEAD, local refs unchanged | Done (snapshot now also covers `.git/config`, HEAD, hooks); the dirty-tree and private-commit cases are tested, detached HEAD and mid-merge only by design (nothing is checked out) |
| | I2 no force push | Done (`T_NOFORCE`, `T_PIPE_09`) |
| | I3 no local-only commit published | Done (`T_PIPE_03`) |
| | I4 truthful results; CLI exit codes | Done; S7 fixed three misreporting edge cases |
| | I5 timeouts, non-interactive | Done (`T_PIPE_12`) |
| | Non-ASCII names, identities, messages | Done |
| | Size gate before any Git command | Done (`T_PIPE_13`) |
| | Coverage: core ≥ 85 %, add-in layer + controller ≥ 60 %, floor enforced | Done (see §3) |
| | Passes under a hostile global Git config; no temp directories left | Done (CI job with `tempdir_guard`) |
| Security and privacy | I6 no credential in config, logs, `.git/config`, helper stores; none visible to hooks; token URLs rejected | Done; plus token out of every process environment (R-21 E4) and an end-to-end scan test |
| | Masked token input; symlink escapes refused | Done (masking live check D1); symlink escapes moot (nothing written into the repository folder) |
| | PRIVACY.md published and linked; publication notice | Done |
| | Every SECURITY.md claim re-verified; private vulnerability reporting enabled | Claims re-verified by the S7 security review; **private vulnerability reporting off** (maintainer) |
| | Release workflow permissions, `persist-credentials: false`, SHA-pinned actions | Done (SHA-pinning *enforcement* setting: maintainer) |
| Fusion and platform | Live procedure passes on Windows 11 (build recorded) | **Pending: the campaign** |
| | macOS passes or is labelled Experimental everywhere | Labelled Experimental everywhere; macOS criteria are *if available* |
| | One toolbar button after Stop/Run ×3 and a forced kill; two installs warn | Implemented and simulated; live K4, K9, K6 pending |
| | Linked components: restorable archive or explicit warning | `.f3z` export with explicit warning; **J2 pending (required)** |
| | Network loss: readable failure within the timeout; Fusion responsive | Implemented and tested; live F2, F4 pending |
| | Load time measured | Live P3 pending |
| User experience | Usability test with 3+ people new to Git | **Pending** (protocol ready: `docs/USABILITY_TEST.md`) |
| | Single history default; snapshots under Advanced; no Force Push or STEP protocol options | Done |
| | OK disabled until valid; no traceback in any dialog; plain first line and next step | Done (simulated); live U1, U13 pending |
| | Success dialog: Open on GitHub, Copy link, short SHA, Fusion version | Done |
| | One display name; original icon with 16/32 px and 120 px | Done |
| Documentation and OSS | README outline; install from the release ZIP; restore, uninstall, size limits, public-repo warning, trademark | Done |
| | Each procedure once; grep guards | Done (guards in the docs check) |
| | CHANGELOG Keep-a-Changelog with credits incl. DiegoV71 | Done |
| | CONTRIBUTING, SUPPORT, issue forms, PR template, Code of Conduct; community profile 100 % | Done (profile 100 %) |
| Distribution | Community Store: install action, icon, screenshots; upgrade from 0.3.x tested; trusted source | Trusted source done; icon via `community-store.json`; **screenshots and Store live checks pending** |
| | Autodesk track | Deferred (decision Q7/Q8) |

## 2. Automated verification (S7, local Windows; CI on the pull request)

See the closing section of the [S7 report](S7_Implementation_Report.md) for the
exact counts, coverage per module and CI run.

## 3. Risks

The [risk register](../RISK_REGISTER.md) was reviewed in full for this
candidate. No risk is High.

The two Medium risks are:
- **R-06** (linked components): accepted conditionally, with J2 required for 1.0.
- **R-18** (the simulated Fusion may differ from Fusion): managed by the live campaign.

New in S7: **R-28**, `.f3z` backups also publish the linked designs. It is mitigated by the notice, the question and PRIVACY.md.

**R-21** stays *not accepted*; its last open route (E4) is mitigated.

## 4. Live campaign and usability

- **[Acceptance matrix](../../tests/ACCEPTANCE_MATRIX.md):**
  - 112 criteria, 102 of them mandatory;
  - organised by the 20 user workflows;
  - each with a requirement or risk reference, prerequisites, procedure and expected result;
  - fields for the actual result, evidence, status and defect;
  - all *Not Run*.
- **[Run order](../../tests/MANUAL_CHECKLIST.md):** about three hours for steps 0–16, starting from 0.4.0.
- **[Fixtures](../../tests/live/README.md):** test designs and disposable repositories.
- **[Usability protocol](../USABILITY_TEST.md).**
- **Defects** found in the campaign are recorded as issues, fixed in focused commits with regression tests, and the affected criteria are re-run. Before 1.0 the complete mandatory suite is repeated on the final candidate.

## 5. Outstanding maintainer actions

1. **Run the live campaign** on the candidate and record the results in `tests/acceptance/criteria.csv`. Include J2, and the usability sessions with 3+ people.
2. **Repository settings:**
   - turn on private vulnerability reporting;
   - add a tag ruleset (block updating and deleting version tags);
   - turn on SHA-pinning enforcement for actions;
   - consider turning off the unused wiki.
3. **When a running-history release is published,** update the repository description (S6 report §5).
4. **Decide the release-candidate naming.** It is 0.9.0, labelled "1.0.0 release candidate 1", because `-rc` versions can't be installed through the Community Store. Say if you prefer a different scheme.
5. **Decide whether to commit `Assets/Branding/Icon-Master.png`**, and which author name to show (README "Zac Cohen" = LICENSE; manifest "Zachary Cohen").
6. **Publishing:** nothing is published. 0.4.0 remains the public release. 0.6.0–0.9.0 are development versions and need your explicit authorization to publish, as does 1.0.0.
7. **Keep DiegoV71 informed** (issue #11) when a candidate is ready for an independent macOS and Community Store test.
