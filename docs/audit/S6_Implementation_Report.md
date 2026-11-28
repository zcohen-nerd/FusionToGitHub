# FusionToGitHub — S6 Implementation Report

**Sprint:** S6 — Documentation and community (development version 0.8.0)
**Branch / PR:** `s6-docs-community` → `main`
**Date:** 2026-11-28
**Strategy:** the maintainer's feature-completion decision of 2026-11-28. Live verification is consolidated; this sprint merges after its automated gates and an independent review. 0.8.0 is not published.
**Status:** implemented. Nothing in the new documentation has been checked against real Fusion yet: live checks W1–W6 (`tests/MANUAL_CHECKLIST.md`, step 14). No screenshots exist yet.

---

## 1. Scope delivered

| Requirement (brief / audit) | Delivered |
|---|---|
| End-to-end backup and restoration guide (DOC-04) | `docs/RESTORE.md`: what a backup contains and doesn't; finding a version (`HISTORY.md`, a file's History, snapshot branches); downloading one file or a whole folder at a version; opening `.f3d`/STEP/STL in Fusion; linked components (R-06); recovery from the local folder (checked: the add-in's local repository has every pushed backup under `origin/<branch>`); read-only Git commands, with the PowerShell redirection warning |
| Consolidate duplicated documentation (DOC-07) | Twelve superseded files removed (listed in the CHANGELOG); each topic now in one place, indexed by `docs/README.md` |
| Installation, upgrades, rollback, configuration, troubleshooting (DOC-09, UX-11, DOC-11) | `docs/INSTALL.md` (requirements, ZIP, Community Store, macOS, update in a running Fusion, rollback including bringing back pre-0.6.0 settings from `.v0-backup`, two copies, a complete uninstall table); `docs/USER_GUIDE.md` (every control in the 0.7.0 dialog, the backup sequence, where backups go, stored tokens, several computers, glossary); `docs/TROUBLESHOOTING.md` (every catalogued message and refusal, by symptom, with safe fixes) |
| Autodesk Fusion terminology | "Autodesk Fusion" throughout; the docs check rejects "Fusion 360" outside a file path |
| Trademark disclaimers (COMP-11) | README footer; non-affiliation in SUPPORT.md |
| Community documentation, support, contribution policies, issue/PR templates (OSS-01/02) | `SUPPORT.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 by reference, private reporting), `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml` (with a required privacy checkbox), `.github/PULL_REQUEST_TEMPLATE.md`; CONTRIBUTING gains docs rules, a screenshots rule, an AI-assistance note and Community Store release notes |
| Screenshots | `docs/SCREENSHOTS.md`: 12 screenshots needed, each **not yet captured**; how to capture them in real Fusion. None was fabricated |
| Privacy, security and platform statements | PRIVACY.md and SECURITY.md updated for 0.7.0 (per-repository identity, the credential file, the design marker, current labels and function names). Platform table in the README (Windows supported, macOS experimental, Git ≥ 2.30) |
| Community Store compatibility (COMP-08 partly) | `community-store.json` with the icon (256 px PNG); release rules in CONTRIBUTING (numeric tags, pre-releases not installable, digest, card text). Publisher guide read 2026-11-28 |
| Overstated claims (DOC-08) | "Automatic" removed; *What it doesn't do*; Teams page rewritten honestly (no locking, no merging, no "conflict resolution") |
| Non-GitHub hosts (FEAT-01) | README *Other Git servers*: work over https, untested |
| Grep guards (S6 acceptance) | `.github/scripts/check-docs.mjs`: no `reset --hard`, no `AddIns/FusionToGitHub`, no "Fusion 360" outside paths, no hard-coded test counts (the CHANGELOG and the audit record are exempt as history) |
| Copilot files (SEC-12) | Already removed in S3; nothing to do |

## 2. Findings during the sprint

- **Rolling back to 0.4.0 needs the old settings.** 0.4.0 reads the settings
  file as `{repository name: profile}`, so the 0.6.0 layout
  (`schemaVersion`, `meta`, `repositories`) would appear to it as three
  strange repositories. The install guide now says to bring back
  `.fusion_git_repos.json.v0-backup` before running 0.4.0 or earlier. Live
  check K3 covers the rollback itself.
- **Private vulnerability reporting is off** for the repository (GitHub API,
  2026-11-28). SECURITY.md already describes the fallback. Turning it on is a
  maintainer setting (see §5).
- **The repository description**, which the Community Store shows on its card,
  says "each push on its own snapshot branch". That is right for 0.4.0, the
  current release, but not from 0.7.0 on. Update it when such a release is
  published (§5).
- **The maintainer's account is already a trusted Community Store source**
  (`trusted-stores.json`), so the trusted-source request (COMP-09) isn't
  needed.
- **Release-candidate versions:** the Store can't install versions with a
  suffix (`-rc`), and `scripts/package.py` requires `X.Y.Z`. Release
  candidates therefore use numeric 0.9.x versions (also the audit's advice);
  see the S7 report.

## 3. Verification

- Docs check: every relative link and anchor, every external URL, and the new
  guards pass (two 403 warnings from sites that refuse automated requests).
- Release check for 0.8.0 passes; ruff clean.
- Test suites: see the pull request (the only code changes are message labels,
  "Use stored token").
- Facts in the new documents were checked against the code: labels, messages
  and defaults in `push_dialog.py`, the catalog in `error_catalog.py`, the
  setup checks, `HISTORY.md`'s format, the uninstall locations, and the
  local-folder recovery (by experiment).

## 4. Live checks added

W1–W6 (`tests/MANUAL_CHECKLIST.md`, step 14):
- installing by following `docs/INSTALL.md`;
- restoring an earlier version by following `docs/RESTORE.md`, including a STEP file;
- labels and messages quoted in the guides match Fusion;
- uninstalling by following the guide;
- capturing the screenshots;
- the Community Store card icon.

## 5. Maintainer actions arising

1. Turn on **Private vulnerability reporting** (Settings → Code security).
2. Turn on **Immutable releases** and a tag ruleset, if not done
   (CONTRIBUTING → Releasing).
3. When a release with the running history is published, update the
   **repository description**, for example: *"Autodesk Fusion add-in: back up
   a design (F3D, STEP, STL and more) to a GitHub repository with one click,
   with a dated history of every version."*
4. Optionally add the `fusion-addin` topic (the Store also recognises it).
5. Capture the screenshots in `docs/SCREENSHOTS.md` during the live campaign.
6. Decide whether `Assets/Branding/Icon-Master.png` should be committed. It
   stays untracked.

## 6. Independent documentation review

An independent review checked every user-facing document against the code.
It confirmed the labels, defaults, paths, limits, error headlines and message
texts, found no destructive or unsafe advice, and found every link and anchor
resolving. Its findings, and what changed:

- **Overclaims fixed:**
  - "a failed backup changes nothing on GitHub" now reads *normally unchanged; check when the message asks*;
  - "STL in millimetres from 0.6.0" now says it depends on the Fusion version;
  - "any current version" of Fusion is replaced by *versions tested will be listed after the live check*;
  - "never designed to need a restart" claims now say *not yet confirmed in Fusion itself*;
  - `.f3z` "isn't available to add-ins" now reads *has no documented API*;
  - "local folder never changed" now reads *your files and branches never changed*.
- **Unverified Fusion and GitHub UI steps** in the restore guide are labelled
  as such (live check W2). Installation and update sections note that 0.6.0+
  is unpublished.
- **Corrections:**
  - DiegoV71's credits now match the CHANGELOG (#11 both reports, #12, #14);
  - the PRIVACY.md date and version are updated;
  - all four cancel outcomes are listed;
  - STL labels are quoted exactly;
  - the `.lock` advice says to close every Git program first;
  - the log-line wording is corrected.
- **Duplicates reduced:** the README links to the installation guide for the
  folder and the Run step; troubleshooting links to the installation guide
  for the folder, Run and two-copies procedures; linked-components detail
  lives in the restore guide. Short summaries of token, log and data-deletion
  facts remain in PRIVACY.md and SECURITY.md, which are the authoritative
  statements for those topics.
- **Readability:**
  - a plain "In short" summary heads SECURITY.md;
  - the glossary gains force-push, clone, origin/main and pull request;
  - sprint labels are removed from the CHANGELOG.
- **Left for the maintainer:** whether the README should name "Zac Cohen" (as
  LICENSE does) or "Zachary Cohen" (as the manifest does).
