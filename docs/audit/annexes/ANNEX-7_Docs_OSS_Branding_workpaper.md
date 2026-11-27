# FusionToGitHub: documentation, open-source maturity and branding audit (read-only)

Repo: `<repo>` on release/0.3.2 at 29a5c17. All paths below are relative to the repo root.

I did not modify any tracked files. Scratch experiments are in `<scratchpad>\docs_ws\` (decoded icon `icon.png`, local git experiment `exp\`).

## Headline
- The docs are badly out of step with the code:
  - The install folder name conflicts with the release package.
  - The add-in name in the Add-Ins list and the button icon are described wrongly.
  - The changelog is advertised as a cumulative logbook; I proved by experiment that it is not.
  - There is no documented way to restore an earlier design.
  - The macOS sign-in path is unsupported.
  - TROUBLESHOOTING.md gives destructive advice (`git reset --hard`).
- The 0.3.2 release is incoherent:
  - The release is empty, its tag is not on `main`, and the code at that tag reports 0.3.1.
  - The packaging workflow failed with "Release tag 0.3.2 does not match manifest 0.3.1".
  - The CHANGELOG has no 0.3.2 entry, and DiegoV71's contribution is not credited anywhere.
- Repo health:
  - Community profile score is 57%.
  - Private vulnerability reporting is disabled (`{"enabled":false}`).
  - None of the usual community files exist (CONTRIBUTING, CODE_OF_CONDUCT, SUPPORT, issue/PR templates, CODEOWNERS).
- SECURITY.md is the strongest document in the repo and should be the model for the rest.

---

## 1. Documentation inventory

| File | Purpose | Audience | Accuracy | Disposition |
|---|---|---|---|---|
| README.md (288 lines) | Landing page, install, first run, limits | End users plus developers | Mostly good; wrong folder name, version claims, changelog/"never overwrites" overstatements, maintainer packaging section after License | **Rewrite** (trim; outline in §4) |
| INSTALL_QUICK.md (52) | Leftover "Organized Repository" install note | Mixed | Wrong folder name; wrong add-in list name; duplicates README | **Delete** (merge into INSTALL) |
| CHANGELOG.md (39) | Release history | Users and maintainers | 0.3.1 says "no functional change" but 59 commits since 0.3 include data-loss fixes; 0.3 entry points at empty release notes; no 0.3.2; no credits | **Rewrite** (Keep-a-Changelog, backfill) |
| SECURITY.md (171) | Credential model, token guidance, reporting | Users and security reporters | Accurate against code (askpass, CredWriteW, delete-token). One exception: the macOS GCM claim | **Keep**; update reporting section after enabling PVR |
| REFACTORING_SUMMARY.md (319) | Internal Oct-2025 code-review log | Maintainer | Historical; misdated "Version 0.3.1" | **Archive or delete** |
| TROUBLESHOOTING_CRASHES.md (211) | Maintainer debugging notes | Maintainer | Contains the maintainer's personal local path (lines 30, 147, 168); fourth folder-name variant `PushToGitHub` (93); "copy entire src folder" (103) | **Delete** (fold useful parts into TROUBLESHOOTING "Add-in won't load") |
| milestones.md (176) | 2025 roadmap | Maintainer | Stale: M5 "no log-level selector" (exists at Push_To_GitHub.py:1207-1220); "macOS Keychain" PAT (88, not implemented); "in sync at 7.7" (143) | **Archive**; move live roadmap to GitHub Issues/Milestones |
| docs/DOCUMENTATION_INDEX.md (288) | Index of docs | All | Stale ("Last Updated Sept 30 2025, Next Review Dec 2025"); 49/16 test counts; reading order conflicts with README | **Delete** (README "More docs" table replaces it) |
| docs/GETTING_STARTED.md (166) | First-run walkthrough | Novices | Wrong folder; "Enable changelog" (no such toggle); default format wrong (says Fusion Archive, actually F3D+STEP+STL); "make sure PAT has access" | **Merge** into INSTALL/README, then delete |
| docs/INSTALLATION.md (298) | Detailed install | Novices | Wrong folder; "GitHub icon" on button; PAT in checklist; Python tests as user steps; 17 tests; unsupported system requirements; uninstall incomplete | **Rewrite** as the single install guide |
| docs/QUICK_REFERENCE.md (193) | Cheat sheet | Users | Invented "🔄 Processing" indicator; generic "keyboard shortcuts"; unhelpful CLI recovery (`git log`/`git checkout`) | **Merge** useful tables into USER_GUIDE, then delete |
| docs/RELEASE_NOTES_DRAFT.md (56) | Unpublished notes for the reliability overhaul | Users | Content shipped in 0.3.1 but was never published | **Merge** into CHANGELOG 0.3.1, then delete |
| docs/TEAM_GUIDE.md (392) | Team workflows | Team leads | Heavy overstatement: PDF export, "Include Changelog" option, unsupported `{your-name}` placeholders. Merging snapshots conflicts (proven). ~40% generic filler (metrics, standups, escalation) | **Rewrite** as a short "Using with a team" page with honest limits |
| docs/TROUBLESHOOTING.md (436) | Problem solving | Users | Wrong log path (298); wrong test/CLI paths (281-292); destructive and outdated advice | **Rewrite** |
| docs/USER_GUIDE.md (397) | Feature reference | Users | UI labels verified correct; changelog "newest entry first" implies cumulative; "2D drawing export on roadmap" unsupported; PAT `repo` scope advice | **Keep and revise** (absorb QUICK_REFERENCE) |
| tests/TESTING.md (442) | 49-case manual QA plan | Maintainer | Python 3.8+ (CI uses 3.10+); "Enable changelog"; PAT-required assumptions | **Keep** for the maintainer, then fix |
| tests/MANUAL_TESTS.md (197) | Fusion smoke checklist | Maintainer and testers | Test 6 "Enable changelog option"; "PAT required for HTTPS"; 16 tests (SUMMARY says 18) | **Keep and fix**; make it the release gate |
| tests/TEST_FRAMEWORK_SUMMARY.md (169) | Meta-summary of the test docs | Maintainer | Counts wrong (18 vs 19); "enterprise-grade… production-ready" | **Merge** into CONTRIBUTING "Testing", then delete |
| .github/agents/*.md (2), .github/prompts/*.md (1) | Generic Copilot agents copied from github/awesome-copilot | Maintainer tooling | Not project-specific; no upstream MIT attribution | **Remove**, or keep with a note in CONTRIBUTING (§3, DOC-21) |
| LICENSE | MIT, "2025 Zac Cohen" | All | OK. Manifest author is "Zachary Cohen" (cosmetic) | **Keep** |

**Overlap count** (same procedure written N times):

| Topic | Copies | Where |
|---|---|---|
| Install procedure | 6 | README, INSTALL_QUICK, GETTING_STARTED, INSTALLATION, TROUBLESHOOTING, TROUBLESHOOTING_CRASHES |
| PAT setup | 7 | SECURITY, README, GETTING_STARTED, INSTALLATION, QUICK_REFERENCE, TROUBLESHOOTING, USER_GUIDE |
| First-run walkthrough | 4 | README has two by itself (70-97 and 210-220), plus GETTING_STARTED and INSTALLATION |
| Troubleshooting sections | 6 | |
| Format tables | 4 | |
| Collaboration sections | 4 | |
| Test counts | 5 different numbers (17, 18, 19 actual, 16, 49) | |

User-facing docs total about 2,600 lines for a one-button add-in (all Markdown is about 4,800 lines). The previous audit fixed USER_GUIDE's log path (PR #3) but missed TROUBLESHOOTING:298. The drift is structural, not a one-off.

**Links:** `check-docs.mjs` passes (21 files; one 403 warning on github.com/signup). About 15 cross-references are plain backticked filenames rather than links, so the checker never sees them (DOC-18).

---

## 2. Doc-vs-code discrepancies

| Doc file:line | Claim | Actual behavior (file:line) | Verdict |
|---|---|---|---|
| README:58; GETTING_STARTED:47; INSTALLATION:269-279; INSTALL_QUICK:9-14; TROUBLESHOOTING:18-19 | Create add-in folder `FusionToGitHub` | Entry files are `Push_To_GitHub.py` / `.manifest`. The release ZIP prefix is `Push_To_GitHub/` (release.yml, README:282-285 "folder name Fusion expects"). TROUBLESHOOTING_CRASHES:93 uses `PushToGitHub` | **Wrong / conflicting.** Autodesk's rule that folder, .py and .manifest names match makes this likely to break loading; not reproduced in Fusion |
| README:62; GETTING_STARTED:65; INSTALLATION:301; INSTALL_QUICK:28; TROUBLESHOOTING:32 | Find "Push to GitHub (ZAC)" in the Add-Ins list | That string is the command/button name (Push_To_GitHub.py:130). The Add-Ins list shows the add-in (folder/manifest) name | **Likely wrong** (verify in Fusion) |
| README:64; QUICK_REFERENCE:7; USER_GUIDE:32 | A "Push to GitHub" button in the toolbar | The label is "Push to GitHub (ZAC)", promoted in the UTILITIES ▸ ADD-INS panel (`SolidUtilitiesAddinsPanel`, :134, :2107) | Imprecise |
| INSTALLATION:309 | "Button should show GitHub icon" | `addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "")`: no resource folder, so no button icon (:2066). The SVG is only the manifest icon | **Wrong** |
| README:16; USER_GUIDE:99-113; GETTING_STARTED:10,103 | Automatic logbook; "Every push updates CHANGELOG.md… newest first" | The entry is written on the new snapshot branch (fusion_git_core.py:390-441), then HEAD returns to the original branch (:479-491). Each branch's CHANGELOG holds only its own entry; `main` never gets one | **Misleading.** Proven: two CLI pushes gave two branches with one entry each |
| GETTING_STARTED:121-124; MANUAL_TESTS Test 6; TEAM_GUIDE:131 | "Enable changelog" / "Include Changelog" option | No toggle exists; the changelog is always written | **Wrong** |
| TEAM_GUIDE:130 | Export formats include PDF | `available_formats` = f3d, step, iges, sat, stl (Push_To_GitHub.py:975-981) | **Wrong** |
| TEAM_GUIDE:44,69-71 | `{your-name}`, `{designer-name}`, `{version-number}` placeholders | Only `{filename}` and `{timestamp}` (fusion_git_core.py:43-47; dialog_helpers.py:193-209). The commit template also supports `{branch}` (:394), which is undocumented for users | **Wrong.** Braces survive in subfolders as a literal `{your-name}` folder |
| README:117,192; TEAM_GUIDE:99-100,182-184 | Teams can review and merge snapshots into `main` | Merging a second snapshot branch gives add/add conflicts in both `CHANGELOG.md` and the export file (proven in a scratch repo). Binary CAD files cannot be text-merged | **Unsupported workflow, undocumented** |
| README:114 | The branch dropdown "says `main`" | With the recommended empty repo (README:212), the local "Initialize repository" commit is never pushed (dialog_helpers.py:310-318; push sends only the snapshot branch, fusion_git_core.py:448-451). Proven: the remote holds only `fusion-export/*` refs, so GitHub's default branch becomes the first snapshot | **Wrong for empty repos.** INSTALLATION:321 ("Add a README") conflicts |
| README:173-178 | Version consistency, "the Git tag" included, is enforced by CI `T_VERSION` | T_VERSION checks the manifest, Push_To_GitHub.py, CLI and README only (tests/test_runner.py:140-179), not tags. Tag 0.3.2 points at 29a5c17 with manifest 0.3.1 | **False** |
| README:185-187; SECURITY.md:22-29 | GCM ships with Git for macOS; browser sign-in works | No official "Git for macOS" bundles GCM (Xcode CLT and Homebrew git use osxkeychain). Stored token is Windows-only (Push_To_GitHub.py:466-467, :1186, :1196) | **Likely wrong** for typical macOS installs; not reproduced on a Mac |
| TROUBLESHOOTING:298 | Windows log at `%APPDATA%\.PushToGitHub_AddIn_Data` | `os.path.expanduser("~/.PushToGitHub_AddIn_Data")` resolves to `%USERPROFILE%` (Push_To_GitHub.py:124-125). USER_GUIDE:360 is correct | **Wrong** |
| TROUBLESHOOTING:281-292 | `python test_runner.py [--category…]`, `python push_cli.py --help` from project root | Files are `tests/test_runner.py` and `src/push_cli.py` (categories exist) | **Wrong paths** |
| TROUBLESHOOTING:76-77 | Edit `fusion_git_core.py` to set the git path | `GIT_EXE` exists there (:17), but end users are told to edit source code | Accurate but inappropriate |
| TROUBLESHOOTING:250-252 | Re-store token by unchecking and re-checking "Use Stored Token" | Token entry happens via **Manage Token…** with an Update/Delete prompt (:1342-1381) | Wrong |
| TROUBLESHOOTING:239-242 | Look for `git:https://github.com` entries | The add-in's credential is `FusionToGitHub::<repo>` (:437); `git:` belongs to GCM | Partially wrong |
| README:206,256; RELEASE_NOTES:242; TEST_FRAMEWORK_SUMMARY:35,101; INSTALLATION:365 | 18 / 17 automated tests | 19 run and pass (executed `tests/test_runner.py`: 19/19) | Stale |
| TESTING.md:27 | Python 3.8+ | CI uses 3.10–3.12; ruff target py310 | Stale |
| QUICK_REFERENCE:102 | "🔄 Processing" status indicator | Code uses ✅ ⚠️ ❌ ℹ️ only (dialog_helpers.py:62-160) | Invented |
| USER_GUIDE:194 | "2D drawing export is on the roadmap" | Not in milestones.md or issues | Unsupported |
| GETTING_STARTED:85 | Default format is Fusion Archive | Default is F3D+STEP+STL (Push_To_GitHub.py:982) | Wrong |
| INSTALLATION:172-180 | macOS 10.15+, 4 GB RAM, 500 MB | No basis in code or tests | Unsupported |
| README:14,139,198 | Never overwrites; "never rewrites or deletes" history | User-confirmed force push uses `--force-with-lease` (fusion_git_core.py:285-296, :365-379, :448-451) and can overwrite a reused remote branch | Overstated (needs "unless you choose Force Push") |
| CHANGELOG:10 | 0.3.1: "No functional change to the add-in" | 59 commits between tags `0.3` and `0.3.1`, including the data-loss pipeline fix, macOS load fix, new-repo flow (PRs #1-#4) | **Misleading** |
| Verified correct | Dialog labels (Select Repository, Repository Name, GitHub URL, Local Folder, Browse…, Commit Message, Export Formats, Templates, Advanced, Export Subfolder, Branch Name Override, Force Push (skip pull), Use Stored Token, Manage Token…, Logging, Log Level, Open Log File…); config `~/.fusion_git_repos.json`; log path; formats; DWG/DXF exclusion; auto-stash and recovery messages; git identity prompt; multiple saved repos; CLI flags in README:265; SECURITY's token flow | Matches code | OK |

---

## 3. Findings

Priority key: P0 = before any release or merge of PR #13; P1 = next release; P2 = next minor; P3 = backlog; P4 = optional. Effort: S < 1h, M = half a day, L = 1-2 days.

**DOC-01 — Install folder name conflicts with the package and Fusion's naming rule**
- Classification: DOC, UX
- Severity / priority: **High**, P0
- Files: README:58; INSTALL_QUICK:9-14; GETTING_STARTED:47; INSTALLATION:269-279, 458; TROUBLESHOOTING:18-19; TROUBLESHOOTING_CRASHES:93, 103; release.yml (`--prefix=Push_To_GitHub/`)
- Current: users are told to create `FusionToGitHub`. Elsewhere the repo uses `Push_To_GitHub` and `PushToGitHub`, and one doc says copy "the entire src folder" (which creates a folder named `src`).
- Expected: one folder name, `Push_To_GitHub`, matching the .py and .manifest.
- Evidence: the strings above, plus README:282 ("folder name Fusion expects").
- Resolution: make "download `Push_To_GitHub-universal.zip` from Releases, unzip into AddIns" the primary path. Fix all copies and delete the duplicates.
- Alternatives: rename the entry files to FusionToGitHub. Not recommended: it breaks existing installs and the Community Store listing.
- Effort / dependencies: S; depends on DOC-03 (assets on releases).
- Acceptance: `git grep -n "AddIns.FusionToGitHub\|AddIns.PushToGitHub"` returns nothing; a fresh install from the docs loads in Fusion on Windows and macOS.
- Confidence / evidence: High that the docs conflict; Medium-High that loading breaks. Code-verified; the Fusion load behaviour is a documented Autodesk rule, not reproduced here.

**DOC-02 — Add-in name, button label and button icon described incorrectly**
- Classification: DOC, UX
- Severity / priority: Medium, P1
- Files: README:62, 64; INSTALLATION:301, 307-309; USER_GUIDE:32-33; Push_To_GitHub.py:130, 134, 2066
- Current: docs say to find "Push to GitHub (ZAC)" in the Add-Ins list and promise a GitHub-icon button. In fact the button has no icon and its label carries "(ZAC)".
- Expected: docs state the real list name (`Push_To_GitHub`), the real location (UTILITIES ▸ ADD-INS panel) and the real label.
- Resolution: fix the docs, and fix the product with BRAND-01 and BRAND-02 (rename `CMD_NAME`, add a 16/32 px resource folder).
- Effort: S
- Acceptance: a screenshot in the docs matches Fusion.
- Confidence / evidence: High for the icon and label (code-verified); Medium for the list name (needs a Fusion check).

**DOC-03 — Release 0.3.2 is incoherent; README falsely claims CI checks the tag**
- Classification: DOC, OSS
- Severity / priority: **High**, P0
- Files: README:173-178, 288; CHANGELOG (no 0.3.2 entry); fusion_git_core.py:15; src/Push_To_GitHub.manifest; tests/test_runner.py:140-179
- Current:
  - "Latest" release 0.3.2 has an empty body and no assets.
  - Its tag points at 29a5c17, which is only on `origin/release/0.3.2`, and the code there says 0.3.1.
  - The packaging run 45833326393 failed: "Release tag 0.3.2 does not match manifest 0.3.1".
  - No release (0.3, 0.3.1, 0.3.2) has ever had an installable asset.
  - The 0.3 and 0.3.2 release bodies are empty.
  - README:288 says to tag `v0.3.1`, but the existing tags have no `v`.
- Expected: tag = VERSION = manifest = CHANGELOG = README; the release carries the ZIP and its sha256.
- Resolution:
  1. Decide 0.3.2's scope (packaging only).
  2. Bump `VERSION` and the manifest to 0.3.2, and update the README version text.
  3. Add a CHANGELOG 0.3.2 entry with credit (OSS-03).
  4. Merge to `main`, then publish the release from `main`.
  5. Extend T_VERSION, or the release workflow, to check that the CHANGELOG has the version heading.
  6. Write down one tag convention (bare numerals).
- Alternatives:
  - (a) Mark the existing 0.3.2 release "superseded", untick Latest, and ship 0.3.3.
  - (b) Delete the 0.3.2 release and tag (it is minutes old with no assets). This conflicts with the repo's own "tags are immutable" stance, so (a) is preferred.
- Effort: M
- Dependencies: other agents' release findings; PR #13.
- Acceptance: the release workflow succeeds; the Latest release has ZIP + sha256 and notes; README makes no tag claim the tests don't enforce.
- Confidence / evidence: High; verified via gh and git.

**DOC-04 — CHANGELOG misstates history**
- Classification: DOC
- Severity / priority: High, P1
- Files: CHANGELOG.md:8-39; docs/RELEASE_NOTES_DRAFT.md
- Current: 0.3.1 says "Corrective release. No functional change", yet 59 commits since the 0.3 tag include the auto-stash data-loss fix, the macOS load fix, the new-repo clone flow, the askpass hardening and the DWG/DXF removal. The 0.3 entry says "see release notes", which are empty. The real notes sit unpublished in RELEASE_NOTES_DRAFT.
- Resolution: rewrite 0.3.1 as "everything since 0.3", folding in the draft's Highlights. Add an `## Unreleased` section. Delete the draft.
- Effort: S
- Acceptance: a user upgrading from 0.3 can see the data-loss fix in the CHANGELOG.
- Confidence / evidence: High; `git log 0.3..0.3.1`.

**DOC-05 — "Automatic logbook" CHANGELOG is per-branch and never accumulates**
- Classification: DOC (UX follow-up)
- Severity / priority: Medium-High, P1
- Files: README:16; USER_GUIDE:99-113; GETTING_STARTED:10, 103, 121-124; MANUAL_TESTS Test 6; TEAM_GUIDE:131; fusion_git_core.py:390-441, 479-491
- Current: each snapshot branch's CHANGELOG.md has only that snapshot's entry; `main` never gets the log; the docs also describe a toggle that does not exist.
- Evidence: scratch experiment with two `push_cli.py` runs gave two branches, each with one `## …` heading, and no `CHANGELOG.md` on the default branch.
- Resolution: now, reword to "each snapshot includes a CHANGELOG.md entry describing it" and remove the toggle references. Later, as a product decision: drop the per-branch changelog, or maintain a cumulative log on a dedicated `fusion-log` branch or in a GitHub Release.
- Effort: S (docs); M-L (product)
- Acceptance: no doc implies a cumulative log or a toggle.
- Confidence / evidence: High; reproduced.

**DOC-06 — No restore procedure; "version history" overstated**
- Classification: DOC, UX
- Severity / priority: **High**, P1
- Files: README:5, 14, 107-117; QUICK_REFERENCE:178-190; GETTING_STARTED:136-137
- Current: the product promise is "go back to any earlier version", but no doc explains how to get a design back into Fusion. The snapshots are parallel branches off `main`, not a linear history, so the suggested `git log` / `git checkout <commit>` shows almost nothing.
- Expected: a GUI-only how-to: open the repo, pick the snapshot branch, open the `.f3d`, Download, then in Fusion use Upload (or File ▸ Open from my computer). Include comparing two snapshots and finding a snapshot by date.
- Resolution: add a "Get an old version back" section to README and USER_GUIDE, with screenshots. Remove the CLI recovery advice for novices.
- Effort: S-M
- Acceptance: a non-git user can restore a design from the docs alone (usability test).
- Confidence / evidence: High; code-verified.

**DOC-07 — Empty-repo flow: `main` never reaches GitHub, so the default branch becomes a snapshot**
- Classification: DOC (UX follow-up)
- Severity / priority: Medium, P2
- Files: README:76-81, 114, 212; INSTALLATION:321; dialog_helpers.py:310-318; fusion_git_core.py:448-451
- Current: README recommends an empty repo, then tells users to find `main` in the dropdown. INSTALLATION says "Add a README". In practice the remote only ever receives `fusion-export/*` branches.
- Evidence: reproduced against a local bare remote. That GitHub then makes the first pushed branch the default is GitHub's documented behaviour; I did not reproduce it on github.com.
- Resolution: docs should say to tick "Add a README file" (creates `main`), and the two instructions should be reconciled. Product option: push the initial commit when bootstrapping.
- Effort: S
- Acceptance: following README produces a GitHub repo whose default branch is `main`.
- Confidence / evidence: Medium-High.

**DOC-08 — macOS sign-in path unsupported and undocumented**
- Classification: DOC, UX
- Severity / priority: **High**, P1
- Files: README:37, 179-187; SECURITY.md:22-29; QUICK_REFERENCE:152 (SSH listed without setup); Push_To_GitHub.py:466, 1186, 1196; dialog_helpers.py:130
- Current: the docs claim GCM ships with Git on macOS and that a sign-in window appears. Stored tokens are Windows-only. SSH URLs are accepted, but SSH setup is never explained.
- Expected: tested macOS instructions, e.g. `brew install --cask git-credential-manager`, or an SSH-key walkthrough; otherwise state "macOS: experimental".
- Resolution: verify on a Mac, document the prerequisite, and add a macOS row to MANUAL_TESTS. Also mention that `/usr/bin/git` on a fresh Mac is only a stub that prompts to install Xcode CLT.
- Effort: M (needs a Mac)
- Acceptance: a fresh macOS user completes a first push using only the docs.
- Confidence / evidence: Medium; inferred from code and platform knowledge, not reproduced.

**DOC-09 — TROUBLESHOOTING contains destructive, outdated and wrong advice**
- Classification: DOC
- Severity / priority: **High**, P1
- Files (docs/TROUBLESHOOTING.md):
  - :343-346 `git reset --hard HEAD` discards uncommitted work.
  - :205-210 `git add . && git commit -m "Resolve conflicts"` commits conflict markers.
  - :166-176 "Run as administrator" and "Temporarily disable antivirus".
  - :244-248 unsets the global credential helper and sets `manager-core` (deprecated name; current is `manager`).
  - :239-242 and :250-252 wrong credential entry and wrong re-store steps.
  - :76-77 tells users to edit source.
  - :226-228 and :372-375 force-push advice.
  - :298 wrong log path.
  - :281-292 wrong script paths.
  - :40-48 and :406 ask for a Python check, which is irrelevant: the add-in uses Fusion's own Python.
- Resolution: rewrite around symptoms, using the add-in's own recovery messages (fusion_git_core.py:525-541 already prints the exact `git stash pop stash@{n}`). Never suggest `reset --hard`, disabling AV, or editing source. Give a supported git-path override instead (product change), or document "reinstall Git with PATH option".
- Effort: M
- Acceptance: no destructive command without a backup step and a warning; all paths verified by a grep test.
- Confidence / evidence: High; code-verified.

**DOC-10 — Numeric drift (test counts, Python version)**
- Classification: DOC
- Severity / priority: Low, P2
- Files: README:206, 256; INSTALLATION:365; RELEASE_NOTES:242-246; TEST_FRAMEWORK_SUMMARY:23, 35, 101-102; DOCUMENTATION_INDEX:120, 135; TESTING:27
- Current: five different counts in circulation; the suite actually runs 19 tests (executed: 19/19).
- Resolution: remove counts from user docs; keep them only in CI output.
- Effort: S
- Acceptance: `git grep -nE "\b1[6-9] (automated )?tests"` returns nothing.
- Confidence / evidence: High; executed.

**DOC-11 — Anachronistic "0.3.1" stamps on historical documents**
- Classification: DOC
- Severity / priority: Low, P2
- Files: REFACTORING_SUMMARY:1, 316-317; DOCUMENTATION_INDEX:5, 282-284; tests/*.md titles; milestones:143
- Current: an apparent global replace of V7.7 with 0.3.1 has misdated 2025 artifacts as 0.3.1, which shipped 2026-08-31.
- Resolution: archive the historical documents; stop version-stamping living docs.
- Effort: S
- Confidence / evidence: High.

**DOC-12 — Unsupported or overstated feature claims**
- Classification: DOC
- Severity / priority: Medium, P1
- Files:
  - TEAM_GUIDE:5, 10 ("conflict resolution", "contribute simultaneously"), :130 (PDF), :131, :44 and :69-71 (placeholders), :30-31 (branch protection and required reviews on private repos need a paid plan; verify), :229-390 (generic filler).
  - GETTING_STARTED:5, 18, 137.
  - USER_GUIDE:17, 24, 194.
  - QUICK_REFERENCE:102, 106-113.
  - TEST_FRAMEWORK_SUMMARY:170 ("enterprise-grade", "production-ready").
  - README:1 ("Automatic") and :17 ("send anyone a link", which does not work for private repos).
- Resolution: delete or qualify each claim. The TEAM_GUIDE rewrite must say plainly: snapshots are independent; merging two exports of the same design conflicts on both the CAD file and CHANGELOG.md (proven); there is no CAD diff or merge.
- Effort: M
- Acceptance: every capability claim maps to code.
- Confidence / evidence: High.

**DOC-13 — Missing warnings: public exposure, GitHub file-size limits**
- Classification: DOC (UX)
- Severity / priority: **High**, P1
- Files: README:78 (one soft line only); INSTALLATION:320 ("Public or Private (your choice)"); TEAM_GUIDE:29. The code has no size check (`getsize` is used only for empty-file checks).
- Current: nothing warns that a public repo publishes every snapshot of proprietary, client or export-controlled designs, permanently in forks and caches. Nothing mentions GitHub's 100 MB per-file hard block (50 MB warning) or that repos above about 1-5 GB are discouraged; STL "High" exports and assembly F3Ds can exceed these. A push that fails for size leaves a local commit on a snapshot branch, with no documented recovery.
- Resolution:
  - Add a ⚠️ callout in README setup step 1 ("Use Private unless you intend to publish; making a repo private later does not recall forks/clones").
  - Add a "Size limits" known-limit and a recovery note.
  - Product follow-up: a pre-push size check that warns at 50 MB and blocks at 100 MB.
- Effort: S (docs)
- Acceptance: the README setup step contains both warnings.
- Confidence / evidence: High.

**DOC-14 — Prerequisites contradict each other (PAT, Python)**
- Classification: DOC
- Severity / priority: Medium, P1
- Files: INSTALLATION:351-366, 388, 394, 444; GETTING_STARTED:134, 152; USER_GUIDE:323-324; MANUAL_TESTS:10; TEAM_GUIDE:65; TESTING:13
- Current: the PAT is "optional" in SECURITY and README but "generated and saved" in the INSTALLATION checklist and "required" in tests. End users are asked to run Python tests during install and update. USER_GUIDE recommends a classic `repo` scope.
- Resolution: one prerequisite list in INSTALL: Fusion, GitHub account, Git (with GCM on macOS), optional PAT linking to SECURITY. Python only in CONTRIBUTING.
- Effort: S
- Confidence / evidence: High.

**DOC-15 — Duplicated and overlapping docs cause chronic drift**
- Classification: DOC
- Severity / priority: Medium, P2
- Current: see the overlap counts in §1. A prior audit's fixes missed copies.
- Resolution: the architecture in §4, with a single source per topic and links elsewhere.
- Effort: L
- Dependencies: DOC-01, 09, 12, 14
- Acceptance: each procedure exists once; user docs fall from about 2,600 to about 900 lines.
- Confidence / evidence: High.

**DOC-16 — Stale internal files at repo root, including a personal local path**
- Classification: DOC, OSS
- Severity / priority: Medium, P2
- Files: TROUBLESHOOTING_CRASHES.md:30, 147, 168 (the maintainer's personal OneDrive path), :75 ("delete config" silently drops all saved repos), :93, :103; REFACTORING_SUMMARY.md; milestones.md; INSTALL_QUICK.md; docs/RELEASE_NOTES_DRAFT.md
- Resolution: delete, or move to `docs/archive/` with a "historical" banner. Git history preserves them. Move the roadmap to GitHub Milestones.
- Effort: S
- Acceptance: the repo root holds only README, CHANGELOG, LICENSE, SECURITY, CONTRIBUTING (+ CoC/SUPPORT).
- Confidence / evidence: High.

**DOC-17 — Jargon and novice recovery gaps**
- Classification: DOC, UX
- Severity / priority: Medium, P2
- Files: USER_GUIDE:219-258 (stash, rebase, force push); TROUBLESHOOTING passim; QUICK_REFERENCE:178-190; INSTALLATION:452-461
- Missing:
  - Glossary links (README's jargon table is good but isolated).
  - A GUI recovery path (GitHub web UI or GitHub Desktop).
  - How to remove a saved repo: no UI exists, and users must edit `~/.fusion_git_repos.json`.
  - A full uninstall: the steps omit `~/.fusion_git_repos.json`, `~/.PushToGitHub_AddIn_Data/`, `~/FusionGitRepos/` and the `FusionToGitHub::*` credentials.
  - What to do after a failed push.
  - That the commit message pre-fills with the last one used (Push_To_GitHub.py:959-961).
- Resolution: a "Glossary" section, an "Uninstall completely" section and a "Remove a repository from the list" section.
- Effort: M
- Confidence / evidence: High.

**DOC-18 — Unlinked cross-references the link checker cannot verify**
- Classification: DOC
- Severity / priority: Low, P3
- Files: GETTING_STARTED:154, 162-163; INSTALLATION:403-405, 432, 465; QUICK_REFERENCE:194; TROUBLESHOOTING:384-386 (`TESTING.md` actually lives in tests/); TEAM_GUIDE:61, 393; USER_GUIDE:398
- Resolution: convert to relative links.
- Effort: S
- Acceptance: check-docs covers them.
- Confidence / evidence: High.

**DOC-19 — "Never overwrites or rewrites" contradicts Force Push**
- Classification: DOC
- Severity / priority: Low-Medium, P2
- Files: README:14, 139, 197-199 vs :245; fusion_git_core.py:285-296, 365-379, 448-451
- Resolution: "never, unless you choose Force Push or reuse a branch and confirm the force-push prompt".
- Effort: S
- Confidence / evidence: High.

**DOC-20 — "Fusion 360" used throughout; Autodesk now calls it "Autodesk Fusion"**
- Classification: DOC, COMP
- Severity / priority: Low, P3
- Resolution: first mention "Autodesk® Fusion (formerly Fusion 360)", then "Fusion". Keep literal paths (`Autodesk Fusion 360\API\AddIns`) as they are.
- Effort: S
- Dependency: the other agent's Autodesk naming rules.
- Confidence / evidence: High.

**DOC-21 — Generic Copilot agent and prompt files shipped in `.github/`**
- Classification: OSS
- Severity / priority: Low, P3
- Files: .github/agents/principal-software-engineer.agent.md ("MUST offer to create GitHub Issues"); se-technical-writer.agent.md; .github/prompts/suggest-awesome-github-copilot-agents.prompt.md
- Current: unmodified copies from github/awesome-copilot (MIT) without upstream attribution. They are not project-specific, they give contributors' Copilot instructions nobody reviewed, and they add three files to the docs set.
- Resolution: remove them (preferred), or keep them with an upstream-attribution header and a CONTRIBUTING note. They are not end-user material either way; they do not ship in the release ZIP (verified).
- Effort: S
- Confidence / evidence: High.

**DOC-22 — README sends users to the whole-repo ZIP; maintainer packaging steps sit after License**
- Classification: DOC, OSS
- Severity / priority: Medium, P1
- Files: README:50 ("green Code button → Download ZIP"), :280-288; INSTALLATION:238-242 ("Download Release (Recommended)", but there are no assets)
- Resolution: once DOC-03 is done, install from the release asset; move packaging into CONTRIBUTING/RELEASING.
- Effort: S
- Dependency: DOC-03
- Confidence / evidence: High.

**OSS-01 — Private vulnerability reporting disabled**
- Classification: OSS
- Severity / priority: Medium-High, P1
- Files: SECURITY.md:148-165; `gh api …/private-vulnerability-reporting` returns `{"enabled":false}`
- Current: reporters of token-leak bugs must open a public issue saying "details withheld" (the policy names this itself as a placeholder). Secret scanning and push protection are enabled; Dependabot security updates are disabled (fine, since there are no runtime deps).
- Resolution: turn on Settings ▸ Security ▸ Private vulnerability reporting (one click) and point SECURITY.md "Reporting" at the Security tab.
- Effort: S
- Acceptance: the API returns `enabled:true`; SECURITY.md updated.
- Confidence / evidence: High (verified).

**OSS-02 — No community health files (profile 57%)**
- Classification: OSS
- Severity / priority: Medium, P2
- Current: `community/profile` reports CoC, CONTRIBUTING, issue template and PR template all null; there is no CODEOWNERS or SUPPORT. Contributing guidance is one collapsed paragraph (README:270).
- Resolution: see §5.
- Effort: M
- Acceptance: profile at 100%; issue forms require OS/Fusion/Git versions and carry a "no tokens or private designs" warning.
- Confidence / evidence: High.

**OSS-03 — DiegoV71's contribution is not credited**
- Classification: OSS
- Severity / priority: Low-Medium, P1
- Files: CHANGELOG.md; README; release notes
- Current: PR #12 (manifest GUID, packaging command, README section) and issue #11 are credited only in commit message 29a5c17. The 0.3.2 release body is empty. The contributor is reviewing the add-in for the Community Store listing, so good relations matter.
- Resolution: add to the CHANGELOG 0.3.2 entry: "Installable release package and stable add-in ID — thanks @DiegoV71 (#11, #12)". Use GitHub's auto-generated release notes, which list new contributors. Optionally add an "Acknowledgements" line in README.
- Effort: S
- Confidence / evidence: High.

**OSS-04 — Binary release ZIP committed to the repo (PR #13)**
- Classification: OSS
- Severity / priority: Medium, P0 (before PR #13 merges)
- Files: `Push_To_GitHub-universal.zip` (tracked, added in c01237c, re-touched in 29a5c17); .gitignore (`/Push_To_GitHub-universal.zip`)
- Current: the tracked binary contradicts the ignore rule; a hand-built artifact will go stale and diverge from the CI-built asset. PR #13 has an empty description, and its title ("Create …zip") misdescribes the main change (the release workflow).
- Resolution: `git rm --cached` the ZIP in PR #13, retitle it, and add a description.
- Effort: S
- Acceptance: `git ls-files '*.zip'` is empty.
- Confidence / evidence: High.

**OSS-05 — Developer setup and release process undocumented**
- Classification: OSS
- Severity / priority: Low-Medium, P2
- Current:
  - No dev-setup doc; the ruff version is pinned only in ci.yml.
  - No pyproject or requirements-dev; the stdlib-only tests are good.
  - Manual Fusion smoke testing is required but results are never recorded.
  - Version lives in `fusion_git_core.VERSION` plus the manifest plus README plus CHANGELOG plus the tag, and none of this is written down.
  - CI runs only on pushes to main/master and on PRs to them.
- Resolution: CONTRIBUTING sections "Dev setup" (Python 3.10+, git, `python tests/test_runner.py`, `pip install ruff==0.16.5 && ruff check src tests`, `node .github/scripts/check-docs.mjs`) and "Releasing" (a five-step checklist). Optionally a single `requirements-dev.txt` pinning ruff.
- Effort: S-M
- Confidence / evidence: High.

**OSS-06 — Repository settings hygiene**
- Classification: OSS
- Severity / priority: Low, P3
- Current: the wiki is enabled (likely empty; I did not check). The homepage URL is a personal portfolio, and the community profile shows it as "documentation". Delete-branch-on-merge is off.
- Resolution: disable the wiki; point the homepage at README#readme or a docs page; enable auto-delete of head branches. The topics are good; add `autodesk-fusion-addin` and `cad`.
- Effort: S
- Confidence / evidence: Medium (wiki contents unverified).

**BRAND-01 — Product identity is fragmented** (table in §6)
- Classification: UX, COMP
- Severity / priority: Medium, P2
- Current: at least seven user-visible names. The button reads "Push to GitHub (ZAC)", with the maintainer's initials, in the UI and in every message box title (CMD_NAME is used as the messageBox caption throughout).
- Resolution: choose one display name. Changing `CMD_NAME` is safe: `CMD_ID` stays frozen (Push_To_GitHub.py:127-129 comment), so toolbar placement survives. Keep internal identifiers unchanged for compatibility (config, log dir, credential target, CMD_ID).
- Effort: S
- Confidence / evidence: High.

**BRAND-02 — Icon: raster-in-SVG, GitHub mark, code imagery, unused on the button**
- Classification: UX, COMP
- Severity / priority: Medium, P2
- Files: src/AddInIcon.svg (75 KB); Push_To_GitHub.py:2066
- Current:
  - The SVG is a wrapper around a single base64 256×256 PNG; there are no vector paths, so it is not scalable or themable.
  - The artwork is a gear containing GitHub's Invertocat silhouette, a dark blob shape, and `</>` code brackets.
  - The GitHub mark in a third-party app icon conflicts with GitHub's logo usage guidelines (verify with the trademark agent); `</>` signals software, not CAD.
  - The image's provenance and licence are undocumented.
  - The command button has no icon at all (empty resource folder).
- Resolution: commission or draw a simple original vector glyph (for example a part outline plus a branch/snapshot motif, no GitHub mark). Provide 16/32/64 px PNGs in a `resources/` folder for the button, and record provenance in the repo.
- Effort: M
- Confidence / evidence: High that the icon embeds the GitHub mark (visual inspection); trademark conclusion deferred.

**BRAND-03 — Positioning overstates the product**
- Classification: DOC, UX
- Severity / priority: Medium, P1
- Files: README:1, 3, 7; GETTING_STARTED:5, 18; USER_GUIDE:17, 24; TEAM_GUIDE:5; TEST_FRAMEWORK_SUMMARY:170
- Current: "Automatic Design Backups", "Save to Cloud with collaboration", "professional-grade design collaboration… conflict resolution". The product is a manual one-click export-and-commit; there is no scheduling, diffing, CAD merge, locking, BOM/PLM, or reconciliation with Fusion's cloud versions.
- Resolution: adopt the positioning in §6.
- Effort: S
- Confidence / evidence: High.

**BRAND-04 — Third-party trademarks lead the names**
- Classification: COMP
- Severity / priority: Low-Medium, P2
- Current: "FusionToGitHub" and "Push to GitHub" put both Autodesk's and GitHub's marks in the product name; there is no non-affiliation notice.
- Resolution: use the descriptive form "… for Autodesk® Fusion"; add a README footer: "Autodesk and Fusion are trademarks of Autodesk, Inc.; GitHub is a trademark of GitHub, Inc. This project is not affiliated with or endorsed by either." Renaming the repo is optional; GitHub redirects old URLs.
- Effort: S
- Dependency: the other agent's official Autodesk rules
- Confidence / evidence: Medium.

**BRAND-05 — No screenshots or visuals anywhere**
- Classification: DOC, UX
- Severity / priority: Medium, P2
- Current: zero images in any Markdown file (grep). milestones:157 planned them. For a non-git audience, the dialog, the GitHub branch dropdown and the "download a snapshot" flow need pictures.
- Resolution: four to five screenshots plus one short GIF in `docs/images/`, using relative paths (CI already guards against blob URLs).
- Effort: M
- Confidence / evidence: High.

**BRAND-06 — Manifest metadata, docstring and tooltip are weak or stale**
- Classification: UX
- Severity / priority: Low, P3
- Current:
  - Manifest description: "Integrates Fusion with GitHub, allowing users to push designs to repositories." (generic).
  - Author "Zachary Cohen" vs LICENSE "Zac Cohen".
  - Module docstring "Push to GitHub (ZAC) — 0.3" (Push_To_GitHub.py:1-4, stale version).
  - Tooltip "Exports/configures, updates changelog, and pushes design to GitHub." (jargon).
- Resolution:
  - Description: "One-click snapshot of the active design (F3D/STEP/STL/IGES/SAT) committed to your own GitHub repository."
  - Tooltip: "Save a snapshot of this design to your GitHub repository."
- Effort: S
- Confidence / evidence: High.

Informational: commits show AI-assisted authorship (co-author trailers) and a Copilot-agent PR. This is fine; optionally add a one-line policy in CONTRIBUTING ("AI-assisted changes welcome; the submitter is responsible for review and tests").

---

## 4. Proposed documentation architecture

```
README.md               what it is / isn't, requirements, install (release ZIP), first backup,
                        get an old version back, warnings, limits, links  (~200 lines)
CHANGELOG.md            Keep-a-Changelog; Unreleased; credits
SECURITY.md             (keep; update reporting → Security tab)
CONTRIBUTING.md         dev setup, tests, lint, docs check, PR expectations, releasing, AI policy
CODE_OF_CONDUCT.md      Contributor Covenant 2.1 (reference form)
SUPPORT.md              where to ask, what to include, best-effort SLA
LICENSE
docs/
  INSTALL.md            single install/uninstall/update guide (Win + macOS incl. GCM/SSH)
  USER_GUIDE.md         every dialog option + templates/subfolders + recover + remove repo + glossary
  TROUBLESHOOTING.md    symptom → cause → safe fix; "add-in won't load" (from CRASHES); no destructive cmds
  TEAMS.md              short, honest: shared repo, PR review of snapshots, why merges conflict, limits
  PRIVACY.md            (or README section) no telemetry; data only to your GitHub via git; local files list
  images/               screenshots
  archive/              REFACTORING_SUMMARY, milestones, TROUBLESHOOTING_CRASHES, RELEASE_NOTES_DRAFT (or delete)
tests/
  MANUAL_TESTS.md       release gate (Win + macOS rows)
  TESTING.md            full QA plan (maintainer)
.github/
  ISSUE_TEMPLATE/bug_report.yml, feature_request.yml, config.yml
  PULL_REQUEST_TEMPLATE.md
```

Delete or merge: INSTALL_QUICK, DOCUMENTATION_INDEX, GETTING_STARTED (into INSTALL and README), QUICK_REFERENCE (into USER_GUIDE), TEST_FRAMEWORK_SUMMARY (into CONTRIBUTING), RELEASE_NOTES_DRAFT (into CHANGELOG), and the .github/agents and prompts files.

**README outline:**
1. Name, a one-sentence positioning line, and a screenshot of the dialog.
2. **What it does / what it doesn't** (manual snapshots; no CAD merge; not a replacement for Fusion's cloud history).
3. **Before you start:** Fusion, a free GitHub account, Git (Windows: defaults; macOS: plus GCM or SSH). ⚠️ Private-repo warning.
4. **Install** (download `Push_To_GitHub-universal.zip` from Releases, unzip into AddIns, Run, Run on Startup), with a screenshot of the Add-Ins dialog.
5. **First backup** (create repo with README → paste URL → OK → one-time name/email and sign-in).
6. **Everyday use** (three steps).
7. **Get an old version back** (GitHub branch dropdown → download .f3d → Fusion Upload), with a screenshot.
8. **Good to know / limits**: per-push branches; 100 MB per-file limit; repo growth; history durable not immutable; Force Push caveat; per-snapshot CHANGELOG.
9. **Help**: Troubleshooting, Issues, log file location, Security.
10. Docs table · Contributing · License · trademark and non-affiliation notice.

Remove from README: CI and test internals, the packaging command, the "Version consistency" paragraph (keep a version badge only).

---

## 5. Lightweight governance and contribution model (single maintainer)

- **Model:** benevolent single maintainer, best-effort, stated plainly in SUPPORT.md and CONTRIBUTING.md (no response SLA; issues triaged roughly weekly).
- **Must-have, one click:** enable Private Vulnerability Reporting and update SECURITY.md (OSS-01).
- **CONTRIBUTING.md** (about 80 lines):
  - Open an issue before large PRs.
  - Dev setup and the three checks: tests, ruff 0.16.5, docs check.
  - Fusion-UI changes need the MANUAL_TESTS smoke results pasted into the PR.
  - Docs must be updated in the same PR when behaviour or labels change.
  - The release checklist.
  - Credit policy: every external contribution goes in the CHANGELOG with a handle and PR number.
  - AI-assistance note.
  - The upstream attribution note, if the Copilot files are kept.
- **Issue forms:**
  - Bug report: OS, Fusion version, Git version, add-in version, log excerpt, and a required checkbox "I removed tokens and private design data".
  - Feature request.
  - `config.yml` disabling blank issues and linking Troubleshooting and the Security tab.
- **PR template:** checklist with tests / ruff / docs updated / CHANGELOG entry / manual Fusion smoke (if UI touched) / screenshots updated.
- **CODE_OF_CONDUCT.md:** Contributor Covenant 2.1 by reference. It needs an enforcement contact, so use a dedicated alias, or explicitly say "report via GitHub's Report content". Low effort and it completes the profile.
- **SUPPORT.md:** where to ask, what to include, and that the project is not affiliated with Autodesk or GitHub.
- **PRIVACY** (a file or README section): no telemetry; the add-in contacts only your configured Git remote via `git`; local files written (config, log, local repos, Windows Credential Manager entry). Useful for app-store or Community Store listings.
- **Skip or defer:**
  - CODEOWNERS: optional one line `* @zcohen-nerd`; no real value with one maintainer beyond auto-review requests.
  - GOVERNANCE.md, DCO/CLA, Discussions: issues with a `question` label are enough.
  - Disable the wiki.
- **Release discipline:**
  - Releases are cut only from `main`, with the numeric tag equal to `VERSION`.
  - The workflow attaches the ZIP and its sha256.
  - Use GitHub's "Generate release notes" so contributors are credited, then paste a curated summary.
  - Never ship an empty release body.
- **Dependency licensing:**
  - No third-party runtime dependencies (stdlib plus Fusion API plus system git), so the licensing surface is minimal.
  - Action dependencies are SHA-pinned under Dependabot.
  - The open items are icon provenance (BRAND-02) and awesome-copilot attribution (DOC-21).

---

## 6. Naming and branding consistency

| Surface | Current value | Location | Recommendation |
|---|---|---|---|
| Repo / product name in docs | `FusionToGitHub`, "Fusion to GitHub" (README H1) | GitHub; docs | Pick one display name; keep repo slug (redirects if renamed) |
| Add-in folder (entry) | `Push_To_GitHub` (.py, .manifest, ZIP prefix) | src/, release.yml | **Canonical install folder**; keep |
| Folder in docs | `FusionToGitHub`; `PushToGitHub`; "src" | README, INSTALL*, TROUBLESHOOTING*, CRASHES | Replace all with `Push_To_GitHub` |
| Button / command name | "Push to GitHub (ZAC)" | Push_To_GitHub.py:130 | Drop "(ZAC)"; e.g. "Save Snapshot to GitHub" or "Push to GitHub" |
| Command ID | `PushToGitHub_Cmd_ZAC_V7_4` | :129 | Keep frozen (internal; preserves toolbar placement) |
| Manifest description | "Integrates Fusion with GitHub, allowing users to push designs…" | manifest | Rewrite (BRAND-06) |
| Manifest author vs LICENSE | "Zachary Cohen" vs "Zac Cohen" | manifest, LICENSE | Align |
| Module docstring | "Push to GitHub (ZAC) — 0.3" | Push_To_GitHub.py:1 | Remove version from docstring |
| Tooltip | "Exports/configures, updates changelog, and pushes design to GitHub." | :131-133 | Plain-language |
| CLI | "FusionToGitHub 0.3.1" | push_cli.py:84 | Match display name |
| Log dir / file | `~/.PushToGitHub_AddIn_Data/PushToGitHub.log` | :124-125 | Keep (compatibility) |
| Config / default repo dir | `~/.fusion_git_repos.json`, `~/FusionGitRepos` | :83-84 | Keep (compatibility) |
| Credential target | `FusionToGitHub::<repo>` | :437 | Keep (compatibility) |
| Branch prefix | `fusion-export/` | :95 | Keep |
| Host product | "Fusion 360" (docs) vs "Fusion" (manifest) | all docs | "Autodesk® Fusion" on first mention, then "Fusion" |
| Icon | PNG-in-SVG with GitHub mark | src/AddInIcon.svg | Replace with original vector (BRAND-02) |
| GitHub description | "Autodesk Fusion add-in: one-click backup … each push on its own snapshot branch." | repo settings | **Accurate; use as the README tagline** |

**Positioning recommendation.**
- Lead with: *"A one-click snapshot exporter for Autodesk Fusion. It exports the active design (F3D, STEP, STL, IGES, SAT) and commits it, with your note, to its own branch in a GitHub repository you own."*
- Primary value: an independent, off-platform copy of your designs in open formats, with a dated, annotated snapshot trail. It complements, and does not replace, Fusion's built-in version history.
- Secondary value: put CAD exports where your firmware, code and docs already live. Present this as "your exports sit next to your code", not as integration: snapshots don't flow into `main` without manual merges, and those merges conflict.
- Explicitly not: automatic or scheduled backup, CAD diff or merge, multi-user collaboration or locking, PLM/BOM/release management, or a sync of Fusion's cloud versions.
- Avoid: "automatic", "professional-grade collaboration", "conflict resolution", "full version control of your design", "enterprise-grade".

---

## 7. Strengths to preserve
- **SECURITY.md** is accurate against the code. It covers exact storage locations, the askpass design with the token never written to disk, delete-vs-revoke, least-privilege fine-grained PAT guidance, and the CLI `--pat-token` warning. Use it as the style model.
- README's plain-language voice and jargon table; the honest "History is durable, not immutable" and "complement to Fusion's cloud history" limits.
- Every UI label quoted in the docs matches the code; the config and log paths are correct outside TROUBLESHOOTING:298.
- The code's own recovery messages (exact `git stash pop stash@{n}` instructions) and the git-identity prompt for first-time users.
- CI is solid: SHA-pinned actions, Dependabot, a ruff pin with a documented rationale, a docs link and anchor checker, a blob-image guard, a three-Python × two-OS test matrix, and 19/19 tests passing locally.
- The release workflow from PR #12 and 29a5c17 is well designed: version gate, package structure validation, GUID check, sha256. It failed only because the version was not bumped.
- No third-party runtime dependencies; MIT licence; secret scanning and push protection are on; `main` has an active ruleset.
- Changing the display name is cheap: `CMD_ID` is intentionally frozen, so `CMD_NAME` can change without breaking users' toolbar placement.
