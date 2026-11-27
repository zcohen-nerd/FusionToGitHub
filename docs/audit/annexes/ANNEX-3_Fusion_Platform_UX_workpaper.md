# FusionToGitHub audit: Fusion API, cross-platform, UX (release/0.3.2 @ 29a5c17)

**Scope and method.** This was read-only. I read all of `src/Push_To_GitHub.py` (lines 1-2196), plus `dialog_helpers.py`, `diagnostic.py`, `fusion_git_core.py`, the manifest, the SVG, `release.yml`, README, INSTALL_QUICK, GETTING_STARTED, the INSTALLATION update/uninstall section and `tests/MANUAL_TESTS.md`. I checked API usage against the official Autodesk API reference pages, which I downloaded to the scratch dir.
- The `help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/<Class>.htm` URLs now return 404. The working form uses a `fusion_` or `core_` prefix, for example `.../files/fusion_ExportManager.htm`.
- I modified nothing in the repo. Scratch files are under `<scratchpad>\fusion_ws\docs\`.
- Fusion is not installed here, so every runtime claim is marked as unverified where it applies.

**Problems that could block an install or lose data:**
1. **UX-01:** the install docs say to create a folder named `FusionToGitHub`. Autodesk documents that the add-in name comes from the folder, and the main `.py` and `.manifest` must use the same name (`Push_To_GitHub`).
2. **FUS-14:** `controls.addCommand(def, CONTROL_ID)` passes the control ID as the *positionID*. So the cleanup routine (`_delete_all_controls(CONTROL_ID)`) never matches anything.
3. **FUS-01:** STEP AP203/AP214 is a no-op. `STEPExportOptions` has no `applicationProtocol` property.
4. **FUS-02:** every git network operation runs on Fusion's main thread with no timeout and no cancel.
5. **UX-02:** every push creates a branch off `main` that is never merged.
   - The exported files disappear from the local folder after a push.
   - CHANGELOG never accumulates.
   - On an empty remote, `main` is never pushed.
6. **UX-03:** a sticky "Force Push (skip pull)" option plus a free-text branch override can force-push over `main`.
7. **PLAT-01/02:** on macOS there is no reliable git discovery and no supported way to sign in without a terminal.

---

## 1. Fusion API usage table

| # | API call | file:line | Checked against docs | Concern |
|---|---|---|---|---|
| A1 | `adsk.core.Application.get()`, `.userInterface` | Push_To_GitHub.py:189-190, 2033-2036, 2143 | Standard | None |
| A2 | `app.log(msg, level)`; `LogLevels.*` | :198-272, 285-286, 720, 726, 2129, 2156 | core_Application_log.htm; core_LogLevels.htm. The enum has **only** `ErrorLogLevel`, `WarningLogLevel`, `InfoLogLevel`. `log` is static, and writes to TEXT COMMAND by default. | `CriticalLogLevel` at :2129/:2156 does not exist, so the fallback error paths raise AttributeError (FUS-05). The handler at :206-252 uses `getattr` with a default, so it is safe. Every INFO line also goes to the Text Commands window. |
| A3 | `ui.messageBox(msg, title[, MessageBoxButtonTypes.YesNo/YesNoCancel])`, `DialogResults.DialogYes/No` | :744-749, 1369-1384, 1386-1391 | Standard (not fetched) | None |
| A4 | `ui.inputBox(prompt, title, default)` → `(value, cancelled)` | :585, 599, 1342, 1349 | core_UserInterface_inputBox.htm (Python returns a tuple) | The PAT prompt shows the token in plain text (:1350, acknowledged in the code). |
| A5 | `ui.createFolderDialog()`, `.title`, `.showDialog()`, `.folder` | :1486-1490 | core_UserInterface_createFolderDialog.htm | None |
| A6 | `ui.createProgressDialog()`, `.show(title,msg,min,max,delay)`, `.message`, `.progressValue`, `.hide()`, `.cancelButtonText` | :1835-1838, 1904-1906, 1923-1925, 2001-2002 | core_ProgressDialog.htm, core_ProgressDialog_show.htm | **`isBackgroundTranslucencyEnabled` (:1836) is not a documented property.** The documented name is `isBackgroundTranslucent` (FUS-04). The cancel button is hidden (default `isCancelButtonShown=False`), so there is no cancel. Nothing calls `adsk.doEvents()`, so the dialog cannot repaint while git blocks. |
| A7 | `app.activeProduct`; `product.objectType == adsk.fusion.Design.classType()` | :694-699 | core_Application_activeProduct.htm (returns null when no documents are open) | When the CAM workspace is active, the product is not a Design, so the user is told there is "No active Fusion design" (FUS-11). |
| A8 | `design.exportManager`, `design.rootComponent` | :761-762 | fusion_ExportManager.htm | None |
| A9 | `em.createFusionArchiveExportOptions(filename[, geometry])` | :774-778 | fusion_ExportManager_createFusionArchiveExportOptions.htm. Geometry is optional ("root component and its entire contents"). | The TypeError fallback is harmless. Designs with external references need F3Z ([Export designs](https://help.autodesk.com/cloudhelp/ENU/Fusion-Designs/files/ASM-EXPORT-DESIGN.htm)), and the add-in always writes `.f3d` (FUS-06). |
| A10 | `em.createSTEPExportOptions(filename, root)` | :780, 808-821 | fusion_ExportManager_createSTEPExportOptions.htm; fusion_STEPExportOptions.htm. The only properties are `filename`, `geometry`, `wantTempIds`. | `hasattr(opts,"applicationProtocol")` is always False, so the protocol setting is silently ignored (FUS-01). |
| A11 | `em.createIGESExportOptions(filename, root)` / `createSATExportOptions(filename, root)` | :782, 784 | The matching method pages | These may be license-restricted under Personal Use (FUS-08). |
| A12 | `em.createSTLExportOptions(root, filename)`; `opts.meshRefinement = MeshRefinementSettings.MeshRefinementHigh/Medium/Low` | :786-802 | fusion_ExportManager_createSTLExportOptions.htm (argument order geometry, filename is correct); fusion_STLExportOptions.htm; fusion_MeshRefinementSettings.htm (enum names correct) | One combined file (`isOneFilePerBody` defaults to False). `unitType` comes from the design's default units. Binary is the default (FUS-09). |
| A13 | `em.execute(opts)` → bool | :823 | fusion_ExportManager_execute.htm ("Returns true if the export was successful") | The result is checked, along with an existence and size check. Good. |
| A14 | `ui.commandDefinitions.itemById(CMD_ID)` / `addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "")` | :2064-2066 | core_CommandDefinitions_addButtonDefinition.htm. The ID charset `[A-Za-z0-9_]` is satisfied. The resource folder can hold PNG or SVG, and if omitted a default icon is used. | No toolbar icon (FUS-12). The definition is reused if it already exists (good). |
| A15 | `cmdDef.commandCreated.add(h)`, `command.execute.add(h)`, `command.inputChanged.add(h)` | :2069-2070, 2013-2015, 1518-1520 | The pattern matches the documented "global handlers list" guidance (core_Command_validateInputs.htm sample) | Handlers are kept alive in `handlers` and `dialog_handlers`. Good. There is no `validateInputs` handler (FUS-03). |
| A16 | `args.command.isAutoExecute=False`, `isAutoTerminate=True` | :864-865 | Standard | None |
| A17 | `commandInputs.addGroupCommandInput / addDropDownCommandInput / addStringValueInput / addBoolValueInput / addTextBoxCommandInput / addTableCommandInput(id,name,cols,ratio)` and `table.clear/addCommandInput`, `input.deleteMe()` | :869-1226, 1040-1102 | Not fetched one by one; the signatures are consistent with the API | Rendering of the button-style `addBoolValueInput(..., False, "", False)` ("Browse…", "Manage Token…", "Open Log File…") with no resource folder and no `.text` is **unverified**. |
| A18 | `execute_args.executeFailed = True` | :1539, 1580, 1608-1612, 1627-1688, 1726-1887, 1971, 1987, 1996 | core_CommandEventArgs_executeFailed.htm: "the execute operations failed and the commands transaction should be aborted" | Nothing in the docs says this keeps the dialog open, yet the code and messages promise that (FUS-03). The add-in could use `executeFailedMessage` instead of a separate messageBox. |
| A19 | `ui.allToolbarPanels.itemById(PANEL_ID)`, `ui.workspaces.itemById("FusionSolidEnvironment").toolbarPanels.itemById(...)` | :2072-2084, 505-540 | Standard | `SolidUtilitiesAddinsPanel` may not exist (the common ID is `SolidScriptsAddinsPanel`). The fallback covers it. Unverified (FUS-15). |
| A20 | `panel.controls.addCommand(push_cmd_def, CONTROL_ID)` | :2098 | core_ToolbarControls_addCommand.htm: the 2nd argument is **positionID**, and "The ID of the created command control is inherited from the associated command definition." | The control's ID is `CMD_ID`, not `CMD_ID+"_Control"`, so `_delete_all_controls(CONTROL_ID)` (:2095, 2169) and `_find_control_anywhere(CONTROL_ID)` (:2102) never match (FUS-14). |
| A21 | `control.isPromotedByDefault/isPromoted/isVisible`, `control.deleteMe()`, `cmdDef.deleteMe()` | :2106-2109, 2171-2174 | Standard | `stop()` deletes through the saved reference, which works. |
| A22 | `adsk.autoTerminate(False/True)` | :2047, 2092, 2117, 2132 | Standard | Harmless for an add-in. |
| A23 | Threading / `CustomEvent` / `registerCustomEvent` | None used (no `threading` import) | core_CustomEvent.htm, core_Application_registerCustomEvent.htm (the documented way to run worker threads) | All `subprocess.run` calls happen on the main thread (FUS-02). No adsk calls are made off the main thread, which is good. |

## 2. Per-format export assessment

| Format | Call (line) | What it exports (per docs) | Assemblies / linked components | Settings | Success verified? | Concerns |
|---|---|---|---|---|---|---|
| F3D | `createFusionArchiveExportOptions(path)` (:776; fallback `(path, root)` :778) | The root component and all its contents, from the in-memory state including unsaved edits | **Designs with external references must be F3Z** in Fusion's own exporter ("You cannot export Fusion design files that contains external references… only… *.f3z"). The add-in always names the file `.f3d`. API behavior is **unverified**: it could fail, write an archive without the references, or write an f3z under the wrong name. | None | Yes: `execute()` result and size > 0 (:767-768, 823), then the copy is size-checked (:1891) | FUS-06. No record of which Fusion cloud version the file came from (UX-05). Big files can hit GitHub's 100 MB per-file limit (PLAT-07). |
| STEP | `createSTEPExportOptions(path, root)` (:780) | The whole root component | Linked occurrences are presumably included as geometry (unverified) | The AP203/AP214 dropdown (:117-120) **has no effect**: there is no such property (FUS-01). The real protocol is whatever Fusion uses by default (unverified). | Yes | Text format, so it is subject to `core.autocrlf` (PLAT-07). May be blocked under Personal Use (FUS-08). |
| STL | `createSTLExportOptions(root, path)` (:786) | **One combined file** for the whole design (`isOneFilePerBody` defaults to False). Binary by default. | All bodies merged into one mesh; per-body output not offered | `meshRefinement` High/Medium/Low maps to the documented enums (:794-802). `unitType` "is initialized with the default units specified for the Design", so an inch design produces an inch STL, which slicers read as mm (25.4× too small). | Yes | FUS-09. Visibility of hidden bodies and mesh bodies is unverified. A sketch-only design fails, and the push still goes ahead with the other formats (FUS-07). |
| IGES | `createIGESExportOptions(path, root)` (:782) | Whole root component | As STEP | None | Yes | Likely needs a paid license (FUS-08). Text format (PLAT-07). |
| SAT | `createSATExportOptions(path, root)` (:784) | Whole root component (ACIS up to v7 per Autodesk) | As STEP | None | Yes | Likely needs a paid license (FUS-08). Text format. |
| DWG/DXF | Skipped with a warning (:158-164) | Not offered | n/a | n/a | n/a | Mostly right: ExportManager does have `createDXFSketchExportOptions` and flat-pattern DXF/DWG, but no design-level DWG/DXF. The warning text overstates this a little. Informational. |

**Common to all formats:**
- **Filename.** The name is `_safe_base(design.rootComponent.name)` + `.<fmt>` (:771, 1810-1811). The regex `\s+v[\dA-Za-z]+$` strips any trailing word that starts with "v". I ran it: "Air valve"→"Air", "Shelf vertical"→"Shelf", "Tool vA"→"Tool" (FUS-10). Windows reserved names and control characters are not handled (PLAT-08).
- **Overwrite.** Files are exported into a fresh temp dir (:140-147). They are then copied with `shutil.copy2` into the repo subfolder on the export branch (:1889-1890). On a new branch nothing is overwritten. On a reused branch (branch override) the previous same-named files are overwritten without a prompt, which is intended because git keeps history.
- **Partial failure.** A format that fails gets its own messageBox. The push then continues and reports "✅ Push successful" without listing the failure in the summary (FUS-07).

## 3. Platform support matrix and recommended v1.0 policy

| Dimension | Windows 10/11 x64 | macOS 13+ Intel | macOS 13+ Apple silicon |
|---|---|---|---|
| Add-in load (pure Python; `ctypes.wintypes` guarded, :377-432) | OK (code) | OK (code) | OK (code) |
| Git discovery (`GIT_EXE = shutil.which("git") or …`, fusion_git_core.py:17, evaluated once at import) | PATH plus a fallback to `C:\Program Files\Git\bin\git.exe`. Misses per-user installs, GitHub Desktop's bundled git, Scoop (PLAT-04). | A Dock/Finder-launched app gets the launchd PATH (`/usr/bin:/bin:/usr/sbin:/sbin`), so it finds the `/usr/bin/git` CLT stub. If the CLT is absent, each check pops up "install developer tools". Homebrew `/usr/local/bin` is missed (PLAT-01). | Same, and Homebrew's `/opt/homebrew/bin` is missed. |
| Credentials | GCM is bundled with Git for Windows by default. A stored PAT through Credential Manager is available. | **No supported path.** No stored PAT (:439-499, 1186-1196). No macOS git option bundles GCM. Apple git with osxkeychain cannot prompt without a TTY (PLAT-02). | Same |
| Console flashes | `CREATE_NO_WINDOW` used (fusion_git_core.py:51, 79). Good. | n/a | n/a |
| Output decoding | `text=True` uses the locale code page (cp1252), so non-ASCII git output is at risk (PLAT-06) | Usually UTF-8 | Usually UTF-8 |
| Synced folders | OneDrive-redirected Documents is not detected (PLAT-05) | iCloud Desktop & Documents is not detected | Same |
| Line endings | Git for Windows defaults to `core.autocrlf=true`, which rewrites text CAD exports (PLAT-07) | autocrlf usually unset | Same |
| Case / reserved names | Case-insensitive; CON/NUL/COM1 unsafe (PLAT-08) | Case-insensitive APFS by default; NFD normalization handled by git `precomposeunicode` | Same |
| Log viewer | `os.startfile` | `open` | `open` |

**Recommended v1.0 platform policy:**
- **Supported (tested before every release):**
  - Windows 10 22H2 and Windows 11 x64.
  - Current Fusion build (Nov 2026) on a commercial, startup or education license.
  - Git for Windows 2.40+ with bundled GCM, or the add-in's stored PAT.
  - HTTPS `github.com` remotes.
  - The repo in a local, non-synced folder (default `~/FusionGitRepos`).
- **Partially supported (after the PLAT-01/02 fixes; documented limits):**
  - macOS 13+ (Intel and Apple silicon) with git from Xcode CLT or Homebrew **plus GCM installed** (`brew install --cask git-credential-manager` or the .pkg). Until the fixes land, macOS should be labelled "experimental".
  - SSH remotes, only when keys and known_hosts are already set up and there is no passphrase prompt.
  - Fusion Personal Use, limited to F3D and STL.
- **Untested:**
  - Windows on ARM.
  - GitHub Enterprise, GitLab, Bitbucket.
  - Repos inside OneDrive, iCloud or Dropbox (warn).
  - Git LFS.
  - Non-ASCII user names or design names.
  - Designs with external references (F3Z).
  - Very large assemblies (> 100 MB exports).
- **Unsupported:** Linux (Fusion does not run there; the `xdg-open` branch is dead code), the Fusion web client, Drawing and CAM-only documents, and Git older than 2.20.

## 4. UX journey walkthrough (mechanical engineer, no Git experience)

1. **Discover.** The README is well rewritten for non-programmers. GETTING_STARTED still sells "collaboration features" and "Enable changelog" (no such setting) and has a Keyboard Shortcuts section in QUICK_REFERENCE (UX-08).
2. **Install.** The user downloads the *repo* ZIP, creates `…\Autodesk Fusion 360\API\AddIns\FusionToGitHub` and copies the `src` files in (README.md:52-58; INSTALL_QUICK.md:8-10; GETTING_STARTED.md:43-55).
   - The files are named `Push_To_GitHub.*`. Autodesk's rule is that the folder name, main source file and manifest must match.
   - Likely result: the add-in does not appear in Scripts and Add-Ins (UX-01).
   - The release ZIP (`Push_To_GitHub/` prefix, release.yml:47-58) is correct but not what the README tells people to use.
   - Paths use the legacy "Autodesk Fusion 360" folder. It is still searched, but new add-ins default to `…\Autodesk Fusion\API\AddIns`.
3. **Launch.** The button lands in an add-ins panel with the **default icon**, because the resource folder is "" (:2066). The name is "Push to GitHub (ZAC)", and "(ZAC)" means nothing to users. The Design workspace is the only place it appears.
4. **Understand.** The first dialog shows the following.
   - Groups: Repository, Commit Message, Export Formats (lowercase codes `f3d`, `step`… with no descriptions), Templates (`{filename}`/`{timestamp}` with no legend), Advanced (Export Subfolder, Branch Name Override, Force Push (skip pull), Use Stored Token, Manage Token…), and Logging (Log Level, Open Log File…).
   - That is jargon from six concepts on one screen (UX-07).
5. **Configure Git/GitHub.** There is no preflight. Git presence is checked only after OK (:1607).
   - Name and email are asked through two inputBoxes mid-flow (:585-610). The wording is good.
   - GitHub sign-in happens invisibly inside a blocking `git pull` or `git push`, with Fusion frozen (FUS-02). On macOS without GCM it fails (PLAT-02).
6. **Connect repo.** The user pastes the URL and gets the helpful hint "✅ Will use: …" (:1446). "Repository Name" is ambiguous (local nickname or GitHub name?).
   - Clicking OK can run `git clone` **before** any progress UI (:1677 vs :1835), so Fusion looks hung.
   - Validation errors say "Dialog will stay open for corrections" (:1575). It probably closes, and all input is lost (FUS-03).
7. **Export.** The progress dialog shows "Exporting design…" then "Pushing to GitHub…" (:1838, 1905), with no cancel and no repaint.
   - Prompts can pop up during the process: "Local changes detected. We'll stash them temporarily…" and "git pull --rebase failed… force-push this export instead?" (core:227-229, 287-289). The second one offers a destructive action to a novice.
8. **Verify.** Success shows "✅ Push successful to branch: fusion-export/Bracket-20261126-101500", a file list, and "Git flow details" bullets such as "Used --force-with-lease (skip pull)." (:1929-1952).
   - There is no link to open on GitHub and no note of which Fusion version was captured (UX-05).
9. **Find on GitHub.** The repo home page shows `main`, which holds only "Initialize repository", or **is not on GitHub at all** for an empty remote, in which case the first snapshot branch becomes the default.
   - The user has to dig through the branch dropdown (README:146-153).
   - The local folder they chose looks **empty** after the push, because the add-in checks `main` back out (core:480-498). That contradicts GETTING_STARTED "Where are my exported files stored? Locally in the path you specified" (UX-02).
10. **Repeat.** The commit message is pre-filled with the previous one ("Updated design"), so history fills with duplicate messages (UX-06). Each push adds another branch, and the branch list grows without limit.
11. **Recover from an error.** Failures show raw git stderr ("Git operation failed:\ngit push -u origin … failed:\n…", core:474) followed by "Git operations failed. See the messages above for details." (:1974). Nothing is "above" in a modal-box UI.
    - Unexpected errors show a full Python traceback (:1990-1992).
    - Recovery text tells the user to "Run 'git stash pop stash@{0}'" (core:527-540), which needs a terminal.
    - diagnostic.py needs a separate Python install, and its file check omits the required `dialog_helpers.py` (diagnostic.py:51-56).
12. **Update / uninstall.** The update steps are "replace files", then "Test with automated tests" (INSTALLATION.md:270-280).
    - Helper modules may stay cached in `sys.modules` until Fusion restarts (FUS-13).
    - Uninstall leaves `~/.fusion_git_repos.json`, `~/.PushToGitHub_AddIn_Data/` and Credential Manager entries `FusionToGitHub::<repo>` behind. The first two are undocumented (UX-09).

**Recommended simplified dialog** (basic view; Advanced hidden behind a link):

```
+---------------------------------------------------------------+
| Back up to GitHub                                      [?] Help|
+---------------------------------------------------------------+
| Design:   Bracket  (Fusion version v12, saved)   [!] unsaved* |
| Project:  [ my-fusion-designs (github.com/zac/...)       v ]  |
|           [ + Connect a new GitHub project... ]               |
|                                                               |
| What changed?  [ made the bracket holes 5 mm               ]  |
|                (required - shown in your design history)      |
|                                                               |
| Files to include:                                             |
|  [x] Fusion file (.f3d / .f3z)  - full editable design        |
|  [x] STEP (.step)               - for other CAD tools         |
|  [x] STL  (.stl, mm)            - for 3D printing             |
|  [ ] IGES   [ ] SAT             (needs a paid Fusion license) |
|                                                               |
| Saves to:  main  >  designs/Bracket/          [Change...]     |
|                                                               |
|  > Advanced (folder layout, snapshot branches, token, logs)   |
+---------------------------------------------------------------+
|                         [ Cancel ]   [ Back up now ]          |
+---------------------------------------------------------------+
 * "Your design has unsaved changes. The backup will include them,
    but Fusion's own version history will not until you save."

Progress (non-modal, cancellable, step list):
  [done] Exported Fusion file (4.2 MB)
  [done] Exported STEP (1.1 MB)
  [....] Uploading to GitHub...  (Cancel)

Success:
  Backed up "Bracket" (Fusion v12) to GitHub.
  [ Open on GitHub ]  [ Open local folder ]  [ Copy link ]
```

Advanced section: export subfolder template; "Save each backup as a separate snapshot branch" (off by default; when on, show the branch template); branch override (validated, with a hard block on the default branch); Windows-only stored token; log level and Open Log. "Force push" is removed from the UI. If it is kept, it should be per-push only, never persisted, and require typing the branch name to confirm.

**Recommended first-run flow (wizard on first click, or when no project is configured):**
```
Step 1  Checking your computer
        [ok] Git found (C:\Program Files\Git\cmd\git.exe, 2.47)
        [!!] Git not found -> [Download Git]  [I installed it - check again]
        [ok] Sign-in helper found (Git Credential Manager)
        (mac without GCM -> "Install the GitHub sign-in helper" + link)
Step 2  Who are you?   Name [      ]  Email [      ]   (only if missing)
Step 3  Connect GitHub  Paste project address [ https://github.com/... ]
        [Test connection]  -> opens browser sign-in once;
        result: "Connected as zac - you can write to this project"
Step 4  Where to keep local copies  [~/FusionGitRepos/my-fusion-designs]
        (warning if inside OneDrive / iCloud / Dropbox)
Step 5  Done -> "Back up this design now?"  [Back up]  [Later]
```

## 5. Findings

Field order in each block: **Class / Sev / Priority** · **Where** · **Current** · **Expected** · **Evidence** · **Repro** · **Root cause** · **Impact** · **Fix** · **Alternatives/tradeoffs** · **Effort** · **Deps** · **Acceptance** · **Confidence** · **Status**.

### Fusion API integration

**FUS-01: The STEP protocol setting (AP203/AP214) does nothing**
- BUG/UX · Medium · P2 · Push_To_GitHub.py:107-121, 808-821; UI rows :1079-1101.
- **Current:** the dropdown is offered and saved per repo. The code then does `if hasattr(opts, "applicationProtocol"):` and skips the assignment silently.
- **Expected:** offer only settings that exist, or set them through a supported API.
- **Evidence:** fusion_STEPExportOptions.htm lists only `filename`, `geometry`, `wantTempIds`, `isValid`, `objectType`.
- **Repro:** pick AP203, export, and inspect the `FILE_SCHEMA` header in the .step. It will not change (needs live Fusion).
- **Root cause:** a property assumed without checking the docs.
- **Impact:** users think they control STEP compatibility.
- **Fix:** remove the STEP row from `FORMAT_SETTINGS_OPTIONS`; ignore and migrate saved `formatSettings.step`; state the actual protocol in Help once it is verified.
- **Alternatives:** keep the row read-only as information.
- **Effort:** S. **Deps:** none.
- **Acceptance:** no STEP protocol input in the UI; old configs load without error; a unit test asserts there is no step option.
- **Confidence:** High. **Status:** confirmed (docs); file-header check unverified.

**FUS-02: Git network operations block Fusion's UI thread with no timeout and no cancel**
- REL/UX/PERF · High · P1 · fusion_git_core.py:60-67 (`subprocess.run` with no `timeout`), :79-85; Push_To_GitHub.py:1677 (clone before progress UI), :1835-1921.
- **Current:** clone, pull, push, credential sign-in and GCM browser flows all run synchronously inside the execute handler. The progress dialog has no cancel button, and nothing calls `adsk.doEvents()`. An unanswered credential window or a stalled network hangs Fusion indefinitely.
- **Expected:** a responsive UI, step-level progress, a cancel option and bounded waits.
- **Evidence:** there is no `threading` or `timeout` anywhere in `src/`. Autodesk documents `CustomEvent` as the way to "send an event from a worker thread you've created back to your add-in" (core_CustomEvent.htm).
- **Repro:** set the remote to an unreachable host (e.g. `https://10.255.255.1/x.git`) and push. Fusion stays "Not Responding" until the TCP timeout. Needs live Fusion.
- **Root cause:** a synchronous design.
- **Impact:** looks like a crash. Users kill Fusion and lose unsaved work.
- **Fix:**
  1. Do the export on the main thread, which is required.
  2. Hand git to a worker `threading.Thread`, after collecting all decisions up front (stash consent, reuse consent).
  3. Post progress and results through `app.registerCustomEvent` / `fireCustomEvent`.
  4. Show a cancellable ProgressDialog, polled from the CustomEvent handler.
  5. Add `timeout=` per command (e.g. 60 s local, 300 s network) and `GIT_TERMINAL_PROMPT=0`.
  6. Move clone under the progress UI.
- **Alternatives:** a minimal fix keeps the synchronous flow but adds timeouts, `adsk.doEvents()` between steps and per-step messages. That is cheaper, but the UI still freezes during each call.
- **Effort:** M-L. **Deps:** PLAT-03.
- **Acceptance:** with an unreachable remote, Fusion's viewport still orbits and the user can cancel within 2 s; a timeout yields a plain-language error; normal pushes behave as before.
- **Confidence:** High (code). **Status:** confirmed (code); UI-freeze behavior unverified live.

**FUS-03: "Dialog will stay open for corrections" is very likely false, and input is lost**
- UX/BUG · Medium · P1 · :1572-1581, plus every `executeFailed = True; return` (:1539, 1608-1612, 1627-1688, 1726-1887, 1971, 1987); the comment at :1965-1966.
- **Current:** OK is clicked, validation fails inside `execute`, and the user sees the message "Dialog will stay open for corrections". With `isAutoTerminate=True`, the command ends after `execute`.
- **Expected:** OK is disabled until the inputs are valid, with inline messages, and the dialog never closes on a validation error.
- **Evidence:** the docs say `executeFailed` means the "commands transaction should be aborted", with no mention of keeping the dialog open. `ValidateInputsEventArgs.areInputsValid = False` "the OK button … is disabled forcing the user to correct the inputs".
- **Repro:** choose "Set up new…", type a bad URL, click OK, and see whether the dialog remains. Needs live Fusion.
- **Root cause:** a misunderstanding of the command lifecycle.
- **Impact:** retyping, and a misleading message.
- **Fix:** add a `command.validateInputs` handler that calls the existing `validate_repo_inputs` and sets `areInputsValid`; keep the inline status text boxes; on unrecoverable execute errors set `executeFailedMessage` with plain text.
- **Alternatives:** relaunch the command with values pre-filled (`cmdDef.execute()` after saving a draft to meta).
- **Effort:** S-M. **Deps:** none.
- **Acceptance:** an invalid URL or path greys out OK; nothing in the code promises the dialog stays open.
- **Confidence:** Medium. **Status:** suspected, unverified live.

**FUS-04: Misnamed ProgressDialog property `isBackgroundTranslucencyEnabled`**
- BUG · Low · P3 · :1836.
- **Current/Evidence:** the documented property is `isBackgroundTranslucent` (core_ProgressDialog_isBackgroundTranslucent.htm). The line has existed since commit 0083a29 (2025-08), so it is probably accepted as a dynamic attribute and does nothing. If the SWIG proxies reject unknown attributes, every push fails into the traceback path.
- **Fix:** rename it to `isBackgroundTranslucent`.
- **Effort:** XS.
- **Acceptance:** a push in live Fusion shows the progress dialog with no exception.
- **Confidence:** High on the name. **Status:** confirmed (docs); runtime effect unverified.

**FUS-05: `LogLevels.CriticalLogLevel` does not exist**
- BUG · Low · P3 · :2129, :2156.
- **Current:** the fallback logging in `run()`/`stop()` would raise AttributeError and hide the original error.
- **Evidence:** core_LogLevels.htm lists Error=0, Warning=1, Info=2 only.
- **Fix:** use `ErrorLogLevel`.
- **Effort:** XS.
- **Acceptance:** grep shows no `CriticalLogLevel`/`DebugLogLevel` direct references.
- **Confidence:** High. **Status:** confirmed (docs).

**FUS-06: Designs with external references (linked components) need F3Z; the add-in always writes .f3d**
- COMP/BUG · High · P1 · :771, 774-778; formats list :976-983.
- **Current:** the output is always `<name>.f3d`.
- **Expected:** detect external references (e.g. any `design.rootComponent.allOccurrences` item with `isReferencedComponent`) and either export `.f3z` (if the API supports it) or warn clearly: "This design links to other designs; the Fusion file will not include them."
- **Evidence:** the Autodesk help says designs with external references cannot be exported as .f3d, only as .f3z. The API docs say nothing about this. An Autodesk forum thread on exporting true f3z via the API exists ([link](https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/export-true-f3z-files-with-api/td-p/13630808)), but I could not read it (HTTP 403).
- **Repro:** insert a linked component from another cloud design and push with F3D. Then check whether execute returns false, writes an f3z-format file named .f3d, or writes a file without the references, and try importing it on a clean account.
- **Root cause:** a single-part workflow was assumed.
- **Impact:** a "successful" backup that cannot be restored. This is the core value proposition failing silently.
- **Fix:** add reference detection; try `createFusionArchiveExportOptions(path_with_.f3z)` and verify the output; otherwise warn and still export STEP.
- **Effort:** M. **Deps:** live Fusion investigation.
- **Acceptance:** for an assembly with xrefs, the user either gets a restorable archive (verified by re-import) or a warning in the summary.
- **Confidence:** Medium. **Status:** unverified.

**FUS-07: A partial export failure still produces "✅ Push successful"**
- REL/UX · Medium · P1 · :823-835, 1871-1878, 1927-1963.
- **Current:** each failing format opens its own messageBox showing a temp path ("Export failed or empty file for stl: C:\…\Temp\fusion_export_x\Bracket.stl", :828). The pipeline then commits whatever did succeed and reports success. The failure is not included in `export_warnings`.
- **Expected:** collect the failures; ask whether to continue with the partial set before git runs, or make "all requested formats" a precondition; list failures in the summary and in CHANGELOG.
- **Repro:** a sketch-only design with STL selected (needs live Fusion).
- **Root cause:** `export_fusion_design` returns only the successes.
- **Fix:** return `(exported, failures)`; show one consolidated pre-commit prompt; include failures in the summary.
- **Effort:** S.
- **Acceptance:** a forced STL failure gives a single prompt and the summary lists "STL: not exported (no solid bodies)".
- **Confidence:** High. **Status:** confirmed (code).

**FUS-08: License-tier export restrictions are not detected**
- COMP/UX · Medium · P2 · defaults :983; error :828/834.
- **Current:** Personal Use users get generic "Export failed" messages for IGES/SAT and possibly STEP. STEP is in the default format set.
- **Evidence:** Autodesk's [Supported file formats](https://help.autodesk.com/cloudhelp/ENU/Fusion-Designs/files/TPD-SUPPORTED-FILE-FORMATS.htm) page and its 2020 [blog post that STEP stays for personal use](https://www.autodesk.com/products/fusion-360/blog/changes-to-fusion-360-for-personal-use/) disagree about STEP. The search summary says IGES/SAT need a paid license.
- **Fix:** on failure, mention the license as a probable cause; label IGES/SAT "may need a paid Fusion license"; consider defaulting to F3D + STL only.
- **Effort:** S.
- **Acceptance:** on Personal Use, a failed IGES export shows the license hint.
- **Confidence:** Medium. **Status:** unverified.

**FUS-09: STL units, combined bodies and format choices**
- COMP/FEAT · Medium · P2 · :785-802.
- **Current:** one STL per design. Units follow the design's default units. Binary is the default.
- **Evidence:** STLExportOptions `unitType` "is initialized with the default units specified for the Design"; `isOneFilePerBody` "The default is false".
- **Impact:** inch designs import into slicers about 25.4× too small; multi-body prints need manual splitting.
- **Fix:** default `unitType` to millimeters (state it in the summary); add an Advanced option "One STL per body".
- **Effort:** S.
- **Acceptance:** an inch design exports an STL that measures correctly in a slicer.
- **Confidence:** High (docs). **Status:** confirmed (docs); slicer behavior unverified.

**FUS-10: Fragile export filename derivation**
- BUG · Medium · P2 · :706-709, 1810-1811.
- **Current:** `re.sub(r'\s+v[\dA-Za-z]+$','',name)` strips any trailing word beginning with "v". I ran it: "Air valve"→"Air", "Shelf vertical"→"Shelf", "Tool vA"→"Tool".
- **Also:** the name comes from `rootComponent.name` rather than `app.activeDocument.name`/`dataFile.name`; nothing handles control characters, leading "-", reserved names or length; the same base name feeds the branch names.
- **Expected:** strip only `\s+v\d+$`; derive the name from the document; apply a full portable-filename policy (PLAT-08).
- **Fix:** change the regex to `r'\s+v\d+$'`; add a `portable_filename()` helper with tests.
- **Effort:** S.
- **Acceptance:** unit tests for "Air valve", "Bracket v8", "CON", "-x", 300-character names.
- **Confidence:** High. **Status:** confirmed (executed regex).

**FUS-11: Active-document validation is late and narrow**
- UX/REL · Medium · P2 · :685-703, 1607-1612, 1677, 1791, 1804-1808.
- **Current:** the git check, identity prompts, a possible **clone/init of a new repo** and a config save all happen before the design check. A CAM-active product reports "No active Fusion design." Nothing checks:
  - whether the design has exportable bodies;
  - unsaved state (`app.activeDocument.isModified`);
  - the Fusion version (`dataFile.versionNumber`).
- **Expected:** validate the document in `commandCreated`, showing a disabled OK with the reason. Fetch the design via `doc.products.itemByProductType('DesignProductType')`. Show "includes unsaved changes" and record the Fusion version in the commit, CHANGELOG and summary.
- **Effort:** S-M.
- **Acceptance:** opening the command with a Drawing or CAM active shows a clear reason; the commit message footer contains "Fusion version: v12 (unsaved changes: no)".
- **Confidence:** High. **Status:** confirmed (code); CAM/Drawing behavior unverified live.

**FUS-12: No toolbar icon; the add-in icon is a raster image wrapped in SVG**
- PKG/UX · Low · P3 · :2066 (`resourceFolder=""`); AddInIcon.svg (75,433 bytes: a single `<image>` with a base64 PNG of 256×256 in a 129×129 viewBox).
- **Evidence:** addButtonDefinition: "if not provided a default icon will be used". UserInterface_UM: icons are a folder of `16x16`/`32x32` (+`@2x` for PNG, plus `-dark_blue`/`-light_gray` theme variants) in SVG or PNG, "SVG… is the preferred format". The manifest's `iconFilename: "AddInIcon.svg"` matches Autodesk's own template.
- **Fix:** add `resources/PushToGitHub/16x16.svg` and `32x32.svg` (true vector; drawn separately for the two sizes); pass `'./resources/PushToGitHub'`; replace AddInIcon.svg with a real vector under 5 KB; update release.yml to include `resources/`.
- **Effort:** S.
- **Acceptance:** the custom icon shows in the panel in both themes; the release ZIP contains `resources/`.
- **Confidence:** High. **Status:** confirmed (code/docs); rendering unverified.

**FUS-13: Generic top-level module names and global `sys.path` cause collisions and stale helpers**
- ARCH/REL · Medium · P2 · :35-76.
- **Current:** `fusion_git_core` and `dialog_helpers` are imported as top-level modules, and `sys.path.insert(0, current_dir)` is used as a fallback. Fusion runs all add-ins in one interpreter, so `sys.modules` keeps the old helpers when the add-in is stopped and restarted after an update. That risks version skew (a new main file with an old core) and name collisions with other add-ins.
- **Expected:** package-relative imports (`from . import fusion_git_core`), as Autodesk's own template does (`from .lib import fusion360utils`), or unique names (`ftg_git_core`).
- **Effort:** S.
- **Acceptance:** update the files, then Stop and Run without restarting Fusion; the log banner shows the new core version.
- **Confidence:** Medium. **Status:** suspected, unverified live.

**FUS-14: `addCommand` is given the control ID as positionID, so toolbar dedupe never works**
- BUG/REL · Medium · P2 · :136, 2095, 2098, 2102, 2169.
- **Current:** the control created this way gets ID `CMD_ID`. `_delete_all_controls(CONTROL_ID)` therefore never finds it, and the fallback `_find_control_anywhere(CONTROL_ID)` never finds it either.
  - After an unclean stop (an exception in `stop()` or a crash mid-reload), the leftover `CMD_ID` control stays.
  - The next `run()` either creates a duplicate button or hits an addCommand error that re-raises (:2104). That leads to `autoTerminate(True)` and an add-in that will not load until Fusion restarts.
  - The cleanup in `stop()` works only because it uses the saved reference.
- **Evidence:** core_ToolbarControls_addCommand.htm: "The ID of the created command control is inherited from the associated command definition"; positionID "Specifies the reference id of the control to position this control relative to."
- **Fix:** `controls.addCommand(push_cmd_def)`; dedupe on `CMD_ID` across all panels; remove `CONTROL_ID`.
- **Effort:** XS.
- **Acceptance:** after killing the add-in mid-session, Run shows exactly one button; a unit test with a mock panel asserts dedupe on `CMD_ID`.
- **Confidence:** High (docs). **Status:** confirmed (docs); duplicate behavior unverified live.

**FUS-15: Manifest and panel housekeeping**
- PKG · Low · P2 (release-gating) · Push_To_GitHub.manifest; fusion_git_core.py:15; :134.
- **Current:**
  - The manifest fields match Autodesk's current template exactly (`autodeskProduct:"Fusion"`, type, id, author, description, version, runOnStartup, supportedOS `windows|mac`, editEnabled, iconFilename). Good.
  - `version` is `0.3.1` on branch `release/0.3.2`. release.yml:22-39 rejects a `v0.3.2` tag unless the manifest and `VERSION` are bumped.
  - `runOnStartup:true` is appropriate for release.
  - `PANEL_ID="SolidUtilitiesAddinsPanel"` may not exist; the fallback to `SolidScriptsAddinsPanel` covers it.
  - The committed `Push_To_GitHub-universal.zip` (c01237c) is listed in .gitignore and will go stale.
- **Fix:** bump the version in both places; log which panel was used; remove the committed ZIP.
- **Effort:** XS.
- **Acceptance:** a release dry-run with tag v0.3.2 passes.
- **Confidence:** High. **Status:** confirmed (code).

### Cross-platform

**PLAT-01: macOS git discovery**
- COMP · High · P1 (P0 if v1.0 claims macOS as Supported) · fusion_git_core.py:17; Push_To_GitHub.py:545-557.
- **Current:** `shutil.which("git") or "git"` is evaluated once at import. Apps launched from Finder/Dock get the launchd PATH, so Homebrew (`/opt/homebrew/bin` on Apple silicon, `/usr/local/bin` on Intel) and MacPorts (`/opt/local/bin`) are not seen. `/usr/bin/git` is Apple's CLT shim, which triggers the "install command line developer tools" GUI prompt whenever the CLT is missing. The error text "Git executable not found or not working. Check PATH or install Git." gives no steps.
- **Expected:** probe an ordered candidate list. Validate the CLT with `xcode-select -p` before calling `/usr/bin/git`. Re-resolve at each push instead of at import. Allow a user override path in config. Give OS-specific instructions.
- **Evidence:** [git-scm macOS install options](https://git-scm.com/install/mac) are Homebrew, MacPorts, Xcode CLT, or a binary installer abandoned since 2.33.
- **Repro:** a Mac with Homebrew git only (no CLT) → push → CLT popup and "Git Not Found".
- **Effort:** S.
- **Acceptance:** a Mac with only Homebrew git is detected without prompts, and the log shows the path.
- **Confidence:** High. **Status:** suspected (well-known launchd PATH behavior), unverified live.

**PLAT-02: No supported macOS sign-in path; docs overstate GCM availability**
- COMP/DOC · High · P1 · Push_To_GitHub.py:439-499 (PAT is Windows-only), 1186-1196; README "Status" section ("Git Credential Manager… the default in modern Git for Windows / macOS installers").
- **Current:** on macOS, HTTPS auth works only if GCM is installed separately or SSH is already configured. Apple git's `osxkeychain` helper cannot ask for a username or token without a TTY, so a first push fails with "could not read Username…".
- **Evidence:** the [GCM install docs](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/install.md) say "GCM is included with Git for Windows"; on macOS it is a separate brew cask or .pkg. No git-scm macOS option bundles it.
- **Fix:**
  1. Detect a credential helper (`git config --get credential.helper`) and GCM presence during preflight.
  2. On a Mac without GCM, show "Install GitHub sign-in helper" with a link.
  3. Add Keychain-backed PAT storage (`security add-generic-password`/`find-generic-password` via subprocess) to reach parity with the Windows token path.
  4. Correct the README.
- **Effort:** M.
- **Acceptance:** a fresh Mac with CLT git plus GCM completes a browser sign-in; without GCM, a clear preflight message appears before any export.
- **Confidence:** High. **Status:** confirmed (docs/code); runtime unverified.

**PLAT-03: Interactive prompts are not suppressed**
- REL · Medium · P1 · fusion_git_core.py:50-67, 147-152.
- **Current:** `GIT_TERMINAL_PROMPT=0` is set only on the PAT path. No `GIT_SSH_COMMAND` with `BatchMode=yes`, no `GCM_INTERACTIVE` policy, and no timeout. With no console, an SSH host-key or passphrase prompt or a terminal credential prompt either fails cryptically or hangs (combined with FUS-02).
- **Fix:**
  - Always set `GIT_TERMINAL_PROMPT=0`.
  - For SSH, set `GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"` (document the tradeoff).
  - Pass `stdin=subprocess.DEVNULL`.
  - Add timeouts.
  - Map known stderr patterns to plain-language messages.
- **Effort:** S.
- **Acceptance:** an SSH remote with an unknown host fails within the timeout and shows a readable message.
- **Confidence:** Medium. **Status:** suspected.

**PLAT-04: Windows git discovery is incomplete**
- COMP · Medium · P2 · fusion_git_core.py:17.
- **Current:** PATH plus `C:\Program Files\Git\bin\git.exe` only. This misses:
  - `%LOCALAPPDATA%\Programs\Git\cmd\git.exe` (per-user/winget user scope);
  - `C:\Program Files (x86)\Git`;
  - Scoop shims;
  - GitHub Desktop's bundled git (`%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe`), which many engineers have instead of Git.

  The resolved path is cached at import, so installing Git while Fusion runs requires restarting Fusion (README says "restart your computer").
- **Fix:** a candidate list (prefer `cmd\git.exe`); re-resolve at each push; log the path and version; a config override.
- **Effort:** S.
- **Acceptance:** a machine with only a per-user Git install is detected.
- **Confidence:** High. **Status:** confirmed (code).

**PLAT-05: Repos in synced folders (OneDrive/iCloud/Dropbox) are not warned about**
- REL · Medium · P2 · dialog_helpers.py:62-164; Browse :1484-1491.
- **Current:** any folder is accepted. A `.git` directory inside OneDrive or iCloud is prone to locked or evicted objects and conflict copies, which corrupts the repo. Users often pick Documents, which is commonly OneDrive-redirected on Windows and iCloud-synced on macOS.
- **Fix:**
  - Detect `%OneDrive%`/`%OneDriveCommercial%` prefixes, `~/Library/Mobile Documents`, `~/Library/CloudStorage/`, and iCloud Desktop/Documents (`~/Library/Mobile Documents/com~apple~CloudDocs` or the "Desktop & Documents" flag).
  - Show a ⚠️ status line and recommend `~/FusionGitRepos`.
- **Effort:** S.
- **Acceptance:** choosing a OneDrive path shows a warning but does not block.
- **Confidence:** Medium-High. **Status:** suspected (general platform knowledge).

**PLAT-06: Subprocess output decoded with the locale code page**
- PLAT/BUG · Medium · P2 · fusion_git_core.py:60-67.
- **Current:** `text=True` with no `encoding`. On Windows the parent decodes git's UTF-8 output as cp1252, which garbles names (e.g. `git config user.name` = "José"). Bytes undefined in cp1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D; e.g. "Ł" = C5 81) raise UnicodeDecodeError, which turns into "Git operation failed". `LC_ALL=C` does not change git's UTF-8 output of user data.
- **Fix:** `encoding="utf-8", errors="replace"`.
- **Effort:** XS.
- **Acceptance:** a test with git `user.name` "Łukasz Żółć" pushes successfully on Windows.
- **Confidence:** Medium. **Status:** suspected.

**PLAT-07: Text CAD formats and line endings, no .gitattributes, no LFS, size limits**
- COMP/PERF · Medium · P2 · fusion_git_core.py:441-452; dialog_helpers.py:247-325.
- **Current:**
  - STEP, IGES, SAT and ASCII STL are text. Under Git for Windows' default `core.autocrlf=true` they get "CRLF will be replaced by LF" handling, so the committed bytes differ from the exported file and cross-platform checkouts differ.
  - Full binary copies are added on every push with no LFS, so the repo grows quickly.
  - GitHub rejects files over 100 MB; the error surfaces as raw stderr.
- **Fix:**
  - During repo setup, write `.gitattributes` with `*.f3d *.f3z *.step *.stp *.iges *.igs *.sat *.stl *.3mf binary`.
  - Pre-check file sizes (warn at 50 MB, block at 100 MB with guidance).
  - Document LFS as an advanced option.
- **Effort:** S.
- **Acceptance:** a STEP exported on Windows is byte-identical after checkout on macOS; a 120 MB export gets a friendly pre-push message.
- **Confidence:** High. **Status:** confirmed (code); size behavior per GitHub policy.

**PLAT-08: Windows reserved names, long paths, case collisions**
- COMP · Low · P3 · :706-709, 771; dialog_helpers.py:167-190.
- **Current:**
  - Design names such as CON, NUL, AUX, PRN, COM1-9 and LPT1-9 (with any extension) fail on Windows.
  - Trailing dots or spaces in subfolder segments are not rejected.
  - Deep repo paths plus subfolder templates can exceed MAX_PATH (Fusion's embedded Python long-path support is unverified).
  - "Bracket" and "bracket" collide on Windows and macOS.
- **Fix:** a portable-name helper shared with FUS-10 (prefix reserved names with `_`, strip trailing dots and spaces, cap at about 100 characters); warn when the full path exceeds 240 characters.
- **Effort:** S.
- **Acceptance:** unit tests pass.
- **Confidence:** High. **Status:** confirmed (code).

### UX and human factors

**UX-01: Install instructions likely produce a non-loading add-in (folder name mismatch)**
- DOC/PKG · High · P0 · README.md:52-58; INSTALL_QUICK.md:8-22; GETTING_STARTED.md:43-55; INSTALLATION.md:92-98, 292-293; TROUBLESHOOTING.md:18-19; TROUBLESHOOTING_CRASHES.md:93 (uses yet another name, "PushToGitHub").
- **Current:** "Create a new folder there called `FusionToGitHub`" holding `Push_To_GitHub.py`/`.manifest`. Users are told to use the repo ZIP rather than the release asset. Paths use the legacy "Autodesk Fusion 360" folder.
- **Expected:** download the release `Push_To_GitHub-universal.zip` and unzip so the result is `AddIns/Push_To_GitHub/Push_To_GitHub.manifest`; or use the Scripts and Add-Ins "+" link option.
- **Evidence:** WritingDebugging_UM: "The name is defined by the name used for the main directory. The primary source file, and the manifest file also have this name." Current default path: `%appdata%\Autodesk\Autodesk Fusion\API\AddIns` (the legacy path is still searched).
- **Repro:** follow the README exactly on a clean machine and check whether the add-in is listed.
- **Fix:** rewrite the install steps around the release ZIP; use a single folder name everywhere; add a screenshot of the expected tree.
- **Effort:** XS.
- **Acceptance:** a novice following the README sees "Push_To_GitHub" in Scripts and Add-Ins on Windows and on macOS.
- **Confidence:** Medium-High. **Status:** confirmed (docs requirement); load failure unverified live.

**UX-02: The snapshot-branch model hides results**
- ARCH/UX · High · P1 · fusion_git_core.py:303-346, 382, 390-424, 448-452, 480-498; dialog_helpers.py:313-323; README "Where do my files go on GitHub?"; GETTING_STARTED "Where are my exported files stored? A: Locally in the path you specified".
- **Current:**
  - Each push does `checkout -b fusion-export/<name>-<ts>` from the original branch, commits and pushes only that branch, then checks the original branch back out. The exported files then **disappear from the local folder**, because they are tracked only on the export branch.
  - CHANGELOG.md is prepended on a branch forked from `main`, so each branch's changelog holds one new entry and never accumulates. Merging branches always conflicts at the top of CHANGELOG.
  - For an empty GitHub repo, the local "Initialize repository" commit on `main` is never pushed. The first export branch is then the only branch, and GitHub makes it the default (suspected GitHub behavior).
  - Branches pile up without limit.
- **Expected (for novices):** commit to one branch (the default, or a dedicated `fusion-backups` branch) in a per-design folder (`designs/<name>/`), so GitHub's main page, file history and "History" view show the design's evolution, and the local folder holds the latest files. Snapshot branches become an Advanced opt-in.
- **Fix:**
  1. Add a "Backup mode" setting: *Single history* (default; pull --rebase, then commit to the configured branch, then push) or *Snapshot branches* (current behavior).
  2. Push `main` during setup when the remote is empty.
  3. Write CHANGELOG per design folder on the history branch.
  4. Default the export subfolder to `{filename}`.
- **Alternatives:** keep branches but auto-open a PR (needs API auth), or periodically merge; both add complexity.
- **Effort:** M.
- **Deps:** UX-03, UX-05.
- **Acceptance:**
  - A fresh empty remote, after two pushes of the same design, shows `main` as the default branch.
  - `designs/Bracket/Bracket.f3d` has 2 commits in the GitHub history.
  - The local folder contains the latest files.
- **Confidence:** High (code); the GitHub default-branch claim is Medium. **Status:** confirmed (code); GitHub-side unverified.

**UX-03: Destructive options are poorly guarded**
- UX/REL · High · P1 · Push_To_GitHub.py:1159-1176, 1264, 1749, 1777; fusion_git_core.py:286-299, 318-334, 365-380, 448-451; README ("never deletes or overwrites an earlier backup").
- **Current:**
  - "Force Push (skip pull)" is a plain checkbox that is **saved per repo** (`skipPullDefault`) and silently applies to every later push.
  - "Branch Name Override" accepts `main`; the only guard is "Add this export as a new commit on the existing branch?", which does not mention force.
  - When a pull fails for *any* reason (auth, network, conflict), novices are offered "Would you like to skip pulling and force-push this export instead?"
  - With override set to `main` and skip-pull on, `--force-with-lease` (with no expected SHA) can discard teammates' commits that were already fetched.
- **Expected:** no persistent force option; never force-push the default branch; offer force only for conflicts on an add-in-owned branch, with consequences spelled out and the branch name typed to confirm.
- **Fix:**
  - Stop persisting `skipPull`.
  - Block override to the remote HEAD/default branch, or keep it out of force paths.
  - Classify pull failures (auth/network → no force offer).
  - Rename the option "Overwrite remote branch (dangerous)".
  - Use `--force-with-lease=<ref>:<expected-sha>`.
  - Correct the README claim.
- **Effort:** S-M.
- **Acceptance:** a test shows a reopened dialog has force unchecked; override `main` plus skip-pull is refused; an auth failure never offers force.
- **Confidence:** High. **Status:** confirmed (code).

**UX-04: Jargon, misleading and inconsistent messages**
- UX · Medium · P2.
- **Quotes:**
  - "❌ Missing .git directory at this path." (dialog_helpers.py:123)
  - "⚠️ Provide a Git URL or choose a folder that already contains a .git directory." (:151-152)
  - "Git executable not found or not working. Check PATH or install Git." (Push_To_GitHub.py:551-552)
  - "Path '…' for repo '…' is not a Git repo." (:1830)
  - "Error: Selected repo '…' not found in config." (:1722)
  - "Git operations failed. See the messages above for details." (:1974; there are no messages "above")
  - "Git operation failed:\n" plus raw `git … failed:\n<stderr>` (core:474, 69)
  - "Initial pull --rebase failed; branch was force-pushed." (:1948)
  - "Auto-stashed local changes and restored them afterward." (:1944)
  - "Run 'git stash pop stash@{0}'…" (core:527-540; needs a terminal)
  - Raw Python tracebacks: 'ExecuteHandler failed:\n{traceback}' (:1990-1992, 2018-2021)
  - Inconsistent naming: "Use 'Manage Personal Access Token…'" (:1513, 1798), but the button is "Manage Token…" (:1190)
  - "No action or repository selected." with no title (:1538)
- **Fix:**
  - Build an error catalog that maps git stderr patterns (auth, not found, non-fast-forward, file too large, network) to plain text plus a next step.
  - Show the technical detail behind "Show details" or point to the log.
  - Replace tracebacks with "Something went wrong. Details were saved to the log [Open log]".
  - Make labels consistent.
- **Effort:** M.
- **Acceptance:** a copy review; every user-facing string has a plain-language main line; an automated test checks that no traceback reaches a messageBox.
- **Confidence:** High. **Status:** confirmed (code).

**UX-05: The success message does not help users find or identify what was saved**
- UX/FEAT · Medium · P2 · :1927-1963.
- **Current:** a branch name and file list. There is no GitHub link; no distinction between the Fusion version, the exported files, the commit, the branch and the remote; no commit SHA; and no indication that unsaved changes were captured.
- **Fix:**
  - Build `https://github.com/<owner>/<repo>/tree/<branch>/<subfolder>` from the origin URL.
  - Offer "Open on GitHub", "Open local folder" and "Copy link" (use a custom palette or HTML, or a Yes/No messageBox "Open on GitHub now?").
  - Add the "Fusion version vN" and short SHA.
- **Effort:** S.
- **Acceptance:** after a push, one click opens the exact folder on GitHub.
- **Confidence:** High. **Status:** confirmed (code).

**UX-06: Commit message pre-filled with the previous message**
- UX · Low · P3 · :958-966, 1787.
- **Current:** "Updated design" or the last message is reused, so the history fills with identical messages.
- **Fix:** start empty, with the label "What changed? (required)"; disable OK while it is empty, or fall back to the template including the Fusion version.
- **Effort:** XS.
- **Acceptance:** two consecutive pushes do not reuse text unless the user types it.
- **Confidence:** High. **Status:** confirmed (code).

**UX-07: Dialog information architecture**
- UX · Medium · P2 · :868-1226.
- **Current:**
  - One dialog mixes setup, the per-push message, format codes (lowercase `f3d`, `step`, `iges`, `sat`, `stl` with no descriptions), templates with undocumented placeholders (`{branch}` is supported in commit templates, core:395, but never mentioned), logging (Log Level is a developer setting) and token management.
  - "Repository Name" is ambiguous.
  - "Local Folder" sits next to a "Browse…" bool-button whose rendering with no icon or `.text` is unverified.
  - Emoji labels such as "🆕", "💡 Quick Setup", "✅", "❌" may render inconsistently (unverified).
  - The help text box claims "everything else is automatic!"
- **Fix:** the wireframe in section 4. Move Logging and Templates into Advanced; add a placeholder legend; give each format a human description; label the name field "Name shown in this list".
- **Effort:** M.
- **Acceptance:** a usability test with 3 non-Git users finishes the first backup in under 10 minutes without help.
- **Confidence:** Medium. **Status:** confirmed (code); rendering unverified.

**UX-08: Documentation and diagnostics do not match reality**
- DOC · Medium · P2.
- **Current:**
  - GETTING_STARTED claims "Enable changelog" (no such setting), "Format: Keep default (Fusion Archive)" (the default is F3D+STEP+STL), "Subfolder: Use default" (the default is blank), and "Where are my exported files stored? Locally…" (false after the push, see UX-02).
  - Need-help steps tell novices to "Run the tests: python tests/test_runner.py".
  - QUICK_REFERENCE has "Keyboard Shortcuts" (:106); USER_GUIDE says "appears in your recent commands".
  - diagnostic.py has no `run(context)`, so it cannot run from Fusion's Scripts dialog. It needs a separate Python, and its file check omits `dialog_helpers.py` and `AddInIcon.svg` (diagnostic.py:51-56).
- **Fix:** align the docs with behavior; turn the diagnostics into an in-add-in "Check my setup" command that runs the preflight checks from the first-run flow.
- **Effort:** S-M.
- **Acceptance:** CI's docs check (check-docs.mjs) is extended to catch the claims above; diagnostics run from inside Fusion.
- **Confidence:** High. **Status:** confirmed.

**UX-09: Update and uninstall are incomplete**
- DOC/UX · Low · P3 · INSTALLATION.md:270-296; Push_To_GitHub.py:92, 124-125, 435-436.
- **Current:** no version or update check. Uninstall does not mention `~/.fusion_git_repos.json`, `~/.PushToGitHub_AddIn_Data/` or the Credential Manager target names `FusionToGitHub::<repo>`. "Test with automated tests" is unsuitable for this persona. Stop/Run without restarting Fusion may run stale helpers (FUS-13).
- **Fix:** document all leftovers and their exact names; tell users to restart Fusion after updating; optionally add a "Check for updates" link that reads GitHub Releases on demand.
- **Effort:** S.
- **Acceptance:** following the uninstall steps leaves no files or credentials behind.
- **Confidence:** High. **Status:** confirmed.

**UX-10: No first-run preflight; prompts appear mid-operation**
- UX · Medium · P1 · :1604-1612, 1677, 545-622.
- **Current:**
  - Git presence and identity are checked only after OK.
  - GitHub auth is tested implicitly during `git pull`/`push` on Fusion's blocked UI thread.
  - Clone runs with no progress UI.
  - The first push can show several modal boxes: name, email, a GCM sign-in window (possibly behind Fusion, unverified), and a stash prompt.
- **Fix:** the first-run wizard in section 4, with "Test connection" (`git ls-remote` with a timeout, in a background thread).
- **Effort:** M.
- **Deps:** FUS-02, PLAT-01/02/03.
- **Acceptance:** on a clean machine, all blocking problems are reported before any export, each with a next step.
- **Confidence:** High. **Status:** confirmed (code).

**TEST-01: No native-Fusion or macOS acceptance coverage**
- TEST · Medium · P2 · tests/MANUAL_TESTS.md (197 lines, no macOS section, no xref, unsaved-document or license-tier cases).
- **Fix:** adopt the procedure in section 6 as a release gate for each OS.
- **Effort:** S (write) plus about 2 hours per OS per release.
- **Acceptance:** a signed results template attached to each release.
- **Confidence:** High. **Status:** confirmed.

## 6. Draft manual acceptance test procedure (native Fusion; run on Windows 11 x64 AND macOS 14+ Apple silicon; ideally also macOS Intel)

**Preconditions:**
- A clean OS user account.
- The current Fusion build.
- Machine W: Git for Windows (default installer).
- Machine M1: Xcode CLT git plus GCM via brew cask.
- Machine M2: Homebrew git with no CLT.
- Two empty GitHub repos: A (no README) and B (with README).
- Test designs:
  - "Bracket" (single body, mm)
  - "Air valve" (name test)
  - "Assembly_XRef" (contains a linked component from another design)
  - "Inch Part" (units inches)
  - "Sketch Only"
  - "Large" (export over 100 MB, optional)

**Install and lifecycle:**
1. Download the release `Push_To_GitHub-universal.zip` and unzip it into the AddIns folder. **Expected:** the folder is `Push_To_GitHub/` and contains `Push_To_GitHub.manifest`.
2. Open Scripts and Add-Ins. **Expected:** "Push_To_GitHub" is listed with author, version 0.3.2 and its icon. Click Run. **Expected:** exactly one button in the Design workspace panel, with the custom icon once FUS-12 is fixed. The Text Commands window shows a "Loaded" banner.
3. Stop, then Run, 3 times. **Expected:** still exactly one button and no error dialogs. The log shows the banner each time.
4. Quit and relaunch Fusion (runOnStartup). **Expected:** the button appears with no manual step.
5. Negative test: repeat step 1 with the folder named `FusionToGitHub` (as the README currently says). **Record:** whether the add-in is listed (verifies UX-01).

**Preflight / Git discovery:**
6. W: temporarily rename the Git folder and click the button. **Expected:** a clear "Git not found" message with a download link; no crash.
7. M2 (no CLT): click the button. **Expected (post-fix):** Homebrew git is detected and no "install developer tools" popup appears. **Record:** current behavior (verifies PLAT-01).
8. With a fresh account with no git identity, push. **Expected:** the name and email prompts appear once and later pushes skip them. Cancelling at the email prompt gives "Push cancelled" and nothing is written.

**First backup (repo A, empty remote):**
9. Open "Bracket", click the button, choose "Set up new…", paste `https://github.com/<you>/A` (without .git). **Expected:** the hint "✅ Will use: https://github.com/<you>/A.git"; the name is derived automatically.
10. Enter an invalid URL (`abc`) and click OK. **Record:** whether the dialog stays open and keeps the input, or closes (verifies FUS-03).
11. Valid inputs, OK. **Expected:** a progress dialog appears **before** the clone. On W, GCM shows a browser sign-in once. **Record:** whether Fusion's window responds (try orbiting the viewport) during clone and push (FUS-02), and whether the sign-in window appears in front of Fusion.
12. **Expected:** a success box listing the files. On GitHub, check which branch is the default and whether `main` exists (UX-02). Check the local folder contents after success: are the exported files present?
13. Open the pushed F3D on a different account via Upload. **Expected:** it opens with the timeline intact.

**Formats:**
14. Select all 5 formats and push "Bracket". **Expected:** 5 non-empty files. Open the STEP in a text editor: does `FILE_SCHEMA` change between AP203 and AP214 (FUS-01)? On W, check whether git warns about CRLF and whether the committed STEP's line endings match the original (PLAT-07).
15. "Inch Part" → STL and import into a slicer. **Record:** the dimensions (FUS-09).
16. "Sketch Only" → STL plus F3D. **Expected (post-fix):** one consolidated message saying STL was not exported, and a choice to continue. **Record:** whether "✅ Push successful" appears with STL missing (FUS-07).
17. "Assembly_XRef" → F3D. **Record:** the execute result, the file extension and size, and whether re-importing it elsewhere restores the linked component (FUS-06).
18. "Air valve" → **Record:** the exported filename (FUS-10; expected post-fix: "Air valve.f3d").
19. On a Personal Use license, IGES and SAT. **Record:** the messages (FUS-08).

**Document state edge cases:**
20. Make an unsaved edit, then push. **Expected (post-fix):** an "unsaved changes" note, with the Fusion version recorded in the commit.
21. With a Drawing tab active, look for the button. **Expected:** not shown, or shows a clear reason. With the Manufacture workspace active: same.
22. Open two designs, switch to the second, push. **Expected:** files named after the active (second) design.
23. A brand-new unsaved "Untitled" document. **Expected:** the export works, and the name and any warning are sensible.

**Git flow and safety:**
24. Repo B (has README): push twice. **Expected:** no force options are offered; the success notes do not mention force.
25. Edit README on github.com, then push with Branch Name Override = `main` and "Force Push" checked. **Expected (post-fix):** refused. **Record:** current behavior, and whether the web edit survives (UX-03).
26. Reopen the dialog after step 25. **Record:** whether "Force Push" is still checked (sticky, UX-03).
27. Create an untracked file in the local repo and push. **Expected:** a stash prompt; after the push the file is back.
28. Disconnect the network and push. **Expected:** the failure arrives within the timeout, in plain language, with **no** offer to force-push; Fusion stays responsive (post-fix). **Record:** the time to failure and whether Fusion froze.
29. Revoke the token or credentials, then push. **Expected:** an auth-specific message with a fix.
30. (Windows) Advanced → Manage Token…: add a fine-grained PAT, tick Use Stored Token, push. **Expected:** success with no GCM prompt. Delete the token. **Expected:** "removed". Check the label and message consistency (UX-04).
31. (macOS M1) Push with GCM. **Expected:** a browser sign-in the first time and silent afterwards. Then uninstall GCM and push. **Expected (post-fix):** a preflight message to install the sign-in helper (PLAT-02).
32. Choose a repo path inside OneDrive (W) or iCloud Documents (M). **Expected (post-fix):** a warning (PLAT-05).
33. Use a design and git `user.name` containing non-ASCII characters ("Łukasz", "Halterung für Motor"). **Expected:** success, with correct names on GitHub (PLAT-06).
34. Large export (over 100 MB). **Expected (post-fix):** a pre-push warning or block with guidance. **Record:** the current raw error.

**Logging / update / uninstall:**
35. Logging → Open Log File…. **Expected:** the log opens in the OS default app and contains no token values.
36. Update: replace the folder with a newer build while Fusion runs, then Stop and Run. **Record:** the core VERSION in the log banner (FUS-13). Then restart Fusion. **Expected:** the new version.
37. Uninstall: Stop, delete the folder, restart Fusion. **Expected:** no button. Document the leftover `~/.fusion_git_repos.json`, `~/.PushToGitHub_AddIn_Data/` and Credential Manager `FusionToGitHub::*` entries.

**Pass criteria:** steps 1-4, 8-9, 11-14, 20-24, 27-31 and 35-37 pass on Windows. On macOS, steps 1-4, 7, 9, 11-14 and 31 pass. Every "Record" item is logged with a screenshot.

## 7. Strengths to preserve

- **Exports go through the API correctly.** Every format uses the documented ExportManager calls with the right argument order (including STL's geometry-first form). `execute()` is checked, and files are checked for existence and non-zero size both after export and after copy (:767-768, 823, 1891).
- **Exports stay out of the repo until the branch exists.** Files are exported to a temp dir and placed into the working tree only after stash, pull and branch steps (`materialize_files`, core:384-388), so the auto-stash cannot swallow them. The temp dir is always cleaned up.
- **Repo safety and recovery are careful.**
  - The pipeline aborts a conflicted rebase (core:276, 356).
  - It makes branch names unique automatically (core:336-345).
  - It handles detached HEAD and unborn HEAD.
  - It restores the original branch and stash, and surfaces recovery instructions when it cannot (core:480-547).
  - It writes the config atomically (:670-673) and backs up a corrupt config (:636-646).
- **Handler and toolbar lifecycle follows the docs.** Handlers are kept alive in global lists, and per-dialog handlers are released on the next dialog. `stop()` deletes the control and command definition. The re-run guard and the reuse of an existing command definition are good.
- **Windows hygiene is good.** `CREATE_NO_WINDOW` prevents console flashes. `ctypes.wintypes` is guarded so the add-in loads on macOS (:377-383).
- **Git messages are forced into English** (`LC_ALL=C`), so message matching is stable.
- **The askpass design never writes the token to disk** (core:92-161).
- **Error handling is defensive.** The input-changed handler wraps itself in try/except to avoid silent dialog crashes (:1402-1409).
- **The copy is already friendly in places.** The identity prompts ("Git labels every snapshot with a name…") and the URL hint ("✅ Will use: …") show the right tone for non-Git users.
- **The subfolder path check is separator-aware** (dialog_helpers.py:220-226).
- **Pure helpers are split out for testing.** dialog_helpers and fusion_git_core can be tested without Fusion.
- **Release packaging is sound.** The release ZIP uses the correct `Push_To_GitHub/` prefix, its layout is validated, and a SHA-256 is generated (release.yml).
- **The manifest fields match Autodesk's current template.**

## Sources consulted

- [ExportManager object](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager.htm)
- [createFusionArchiveExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createFusionArchiveExportOptions.htm)
- [createSTEPExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createSTEPExportOptions.htm)
- [createIGESExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createIGESExportOptions.htm)
- [createSATExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createSATExportOptions.htm)
- [createSTLExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createSTLExportOptions.htm)
- [ExportManager.execute](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_execute.htm)
- [STLExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_STLExportOptions.htm)
- [STEPExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_STEPExportOptions.htm)
- [FusionArchiveExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_FusionArchiveExportOptions.htm)
- [MeshRefinementSettings](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_MeshRefinementSettings.htm)
- [LogLevels](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_LogLevels.htm)
- [Application.log](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_log.htm)
- [addButtonDefinition](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CommandDefinitions_addButtonDefinition.htm)
- [ToolbarControls.addCommand](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ToolbarControls_addCommand.htm)
- [ProgressDialog](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog.htm)
- [ProgressDialog.show](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog_show.htm)
- [isBackgroundTranslucent](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog_isBackgroundTranslucent.htm)
- [UserInterface.inputBox](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_UserInterface_inputBox.htm)
- [createFolderDialog](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_UserInterface_createFolderDialog.htm)
- [Application.activeProduct](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_activeProduct.htm)
- [CommandEventArgs.executeFailed](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CommandEventArgs_executeFailed.htm)
- [executeFailedMessage](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CommandEventArgs_executeFailedMessage.htm)
- [Command.validateInputs](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Command_validateInputs.htm)
- [ValidateInputsEventArgs.areInputsValid](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ValidateInputsEventArgs_areInputsValid.htm)
- [Command.doExecute](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Command_doExecute.htm)
- [CustomEvent](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CustomEvent.htm)
- [registerCustomEvent](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_registerCustomEvent.htm)
- [CommandDefinitions.itemById](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CommandDefinitions_itemById.htm)
- [Creating Scripts and Add-Ins / manifest (WritingDebugging_UM)](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm)
- [User Interface Customization / icons (UserInterface_UM)](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/UserInterface_UM.htm)
- [Python Add-In Template](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonTemplate_UM.htm)
- [Export designs (f3d vs f3z)](https://help.autodesk.com/cloudhelp/ENU/Fusion-Designs/files/ASM-EXPORT-DESIGN.htm)
- [Supported file formats](https://help.autodesk.com/cloudhelp/ENU/Fusion-Designs/files/TPD-SUPPORTED-FILE-FORMATS.htm)
- [Autodesk blog: STEP export stays for personal use (2020)](https://www.autodesk.com/products/fusion-360/blog/changes-to-fusion-360-for-personal-use/)
- [Forum: Export true f3z with API](https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/export-true-f3z-files-with-api/td-p/13630808) (HTTP 403; known only from the search snippet)
- [git-scm macOS install options](https://git-scm.com/install/mac)
- [Git Credential Manager install docs](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/install.md)

I treated all web content as data only.