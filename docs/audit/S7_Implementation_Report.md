# FusionToGitHub — S7 Implementation Report

**Sprint:** S7 — release candidate preparation (0.9.0 = 1.0.0 release candidate 1)
**Branch / PR:** `s7-release-candidate` → `main`
**Date:** 2026-11-28
**Strategy:** the maintainer's feature-completion decision of 2026-11-28. This sprint covers everything in S7 that doesn't need live Fusion or other people. The live campaign and usability tests are prepared, not run.
**Status:** feature-complete; features frozen; automated gates pass; **not verified in real Fusion**; not published. See the [readiness assessment](V1_Readiness_Assessment.md).

---

## 1. What S7 did

| Brief item | Done |
|---|---|
| Repository-wide audit against the v1.0 audit and all decisions | [Traceability matrix](V1_Traceability_Matrix.md): all 96 audit backlog findings, with version, status, evidence and live criteria. Definition of Done reviewed item by item in the [readiness assessment](V1_Readiness_Assessment.md) |
| Independent correctness, security, data-integrity, test-quality and documentation reviews | Three reviews of the whole code base (correctness/data integrity, security/privacy, test quality); the documentation was reviewed in S6. Findings and fixes in §2 |
| Resolve release-blocking findings | None was release-blocking; every important and most minor findings were fixed (§2) |
| Run all automated checks | §4 |
| Review the risk register | Full review; R-28 added; every open risk names its live criteria |
| Version surfaces and distribution assets | `check_release.py` (manifest, `VERSION`, README, CHANGELOG), package validation including `resources/`, icons check, `community-store.json` |
| Feature-complete release candidate | 0.9.0, labelled 1.0.0 release candidate 1 (numeric: the Community Store can't install `-rc`); features frozen |
| R-06: archive mechanisms | Research (§3) and `.f3z` export with fallback |
| Consolidated live verification and validation | [Acceptance matrix](../../tests/ACCEPTANCE_MATRIX.md) (112 criteria, 20 workflows, record fields), [run order](../../tests/MANUAL_CHECKLIST.md), [fixtures](../../tests/live/README.md), [usability protocol](../USABILITY_TEST.md) |

## 2. Independent reviews and fixes

**Correctness and data integrity** (whole code base, invariants I1–I5): no
release blockers. Fixed:
- A clean-up failure after a successful push turned it into a reported
  failure, which invited a duplicate backup (verified by the reviewer).
- A case-only rename added a second, case-variant file (verified).
- " vase"/" valve" were stripped from design names as if they were version
  numbers (verified).
- A push timeout was reported as a plain failure. GitHub is now asked whether
  the commit arrived, with three outcomes: arrived (success), not arrived, or
  unknown.
- A cancel while another push moved the branch was reported as "nothing was
  pushed"; it is now "uncertain".
- Declining after an empty repository's first commit said nothing was pushed.
- Summary wording.
- An unguarded `os.remove` in the `.f3z` fallback.

Documented instead of changed:
- The new-repository clone runs on Fusion's main thread (R-04 residual).
- Old file names stay in a design's folder after a rename or format change.
- Temporary references and folders after a hard kill are cosmetic.
- Settings-file edge cases.

**Security and privacy** (whole code base against SECURITY.md, PRIVACY.md and
the risk register): no critical or high issues. Most claims were verified by
experiment. Fixed:
- A repository's `core.alternateRefsCommand` could run during a
  token-carrying fetch (medium). Now off, together with `gc.auto` and
  `maintenance.auto`.
- PRIVACY.md didn't mention that `.f3z` includes linked designs (medium).
  Now covered by PRIVACY.md, the publication notice and R-28.
- On Windows, the credential folder could fall back to `%TEMP%`; it never
  does now.
- Redaction of passwords containing `@`; 40-hex tokens in addresses refused.
- Edited addresses checked; remote SHAs and folder names validated.
- The stale-folder sweep is limited to the user's own folders.
- A `GIT_SSL_NO_VERIFY` in the user's environment is ignored for
  token-carrying commands.

**Test quality**: no blockers; the invariants are proven by real-Git tests.
Acted on:
- The "local folder unchanged" snapshot now also covers `.git/config`,
  `HEAD` and the hooks list.
- An end-to-end scan checks that the token appears in no log, settings or
  Git configuration file.
- The simulated Fusion refuses `exportManager.execute` and
  `activeProduct` off the main thread (assumption 34).

Noted for after 1.0 or the campaign:
- detached-HEAD and mid-merge snapshot scenarios (moot by design, but
  untested);
- an HTTPS end-to-end token push in CI (live D3 covers it);
- linting `test_runner.py` assertions;
- replacing fixed sleeps with polling in timing tests.

## 3. R-06 research (linked components)

- **Autodesk's position:** a design with external references can only be
  exported as `.f3z`, with no documented API.
- **Community evidence:** an add-in (nofuturekid/fusion-export) requests
  `createFusionArchiveExportOptions` with an `.f3z` name for such designs and
  receives an archive named `Name.f3z.f3d` (its issue #33).
- **Older forum answers** say it isn't possible.

The add-in now does the same, corrects the name, falls back to `.f3d`, and
keeps every warning, because nothing is verified live. J2 decides whether
the archive restores the linked designs, and with that R-06.

## 4. Automated verification (local, Windows, final state of the branch)

| Check | Result |
|---|---|
| Unit tests (incl. simulated-Fusion dialog, lifecycle, isolation, real-Git pipeline) | 308 tests, all pass except 3 skipped where they need the real Windows vault or a clone without release tags |
| Integration (`tests/test_runner.py`) | 35/35 |
| Coverage gate | Passes for every module except `credentials.py`, which only CI's Windows job measures with the real vault. Total line + branch coverage 80 %; core 88 %, controller 92 %, dialog 80 %, add-in layer 80 % |
| Lint (ruff 0.16.5) | Clean |
| Release check (0.9.0) | Pass |
| Docs check (links, anchors, external URLs, guards) | Pass |
| Icons (`make_icons.py --check`) | Pass |
| Acceptance matrix (`acceptance.py check`) | Pass: 112 criteria, renders current |
| CI (Windows, macOS, Ubuntu; Python 3.10–3.12; hostile Git config; coverage; package) | See the pull request |

## 5. Not done in S7 (needs Fusion, GitHub settings or people)

- The live campaign: all 112 criteria are *Not Run*.
- Usability sessions X1–X4.
- Screenshots.
- Repository settings: private vulnerability reporting, tag ruleset, SHA-pinning enforcement.
- Publishing anything.

See the readiness assessment §5 for the maintainer's list.
