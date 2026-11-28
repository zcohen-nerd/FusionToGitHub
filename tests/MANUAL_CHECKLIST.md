# Manual Fusion checklist

Run this in **real Fusion on Windows** before publishing a release (CONTRIBUTING
→ Releasing, step 5). The automated tests run the dialog against *simulated*
Fusion objects (`tests/fakes/adsk`); this list covers what only real Fusion can
show.

**A release is not published until every mandatory item passes**, or its
failure is recorded together with a maintainer decision. Items marked
*(if available)* are needed only when you have what they need (the
Community Store, a Mac). macOS is Experimental: report results there in an
issue.

The steps form **one session**, in this order: each step leaves Fusion in the
state the next one needs. It starts from the previous release (0.4.0) so the
upgrade, migration and same-session update checks happen naturally. Expect
about 2 hours.

Every acceptance criterion has an ID: the letter of its original checklist
section and its position there (A1 … M3). The table at the end shows where
each one is checked. R1–R2 are new live checks of the R-21 protections;
U1–U16 cover 0.7.0's dialog, history modes, links and icon (step 4a).

| Item | Value |
|---|---|
| Add-in version (candidate ZIP name and SHA-256) | |
| Previous version installed for the upgrade test | |
| Fusion build (Help → About) | |
| Windows version | |
| Date, tester | |

## 0. Prepare (before starting Fusion)

- A **private** test repository on GitHub, with no other content you need
  (it receives test branches).
- A fine-grained token for **only** that repository (Contents: read and
  write), for step 7.
- The previous release's ZIP (`Push_To_GitHub-0.4.0.zip`) and the candidate
  ZIP, unpacked into two separate folders outside Fusion's AddIns folder.
- In Fusion: a throwaway design in **inch** units, and a second design you
  can insert into it as a linked component.
- Optional: a folder inside OneDrive or Dropbox for step 11.
- Note the other add-ins you normally run, for K7.

## 1. Start on the previous release

1. Install 0.4.0 (UTILITIES → ADD-INS → `+`, or unpack it into the AddIns
   folder), Run it, and tick **Run on Startup**.
2. Set up the test repository with 0.4.0 if it isn't already, and push once.
   This creates the old settings file and the repository-root
   `CHANGELOG.md` that later steps check.

## 2. Update in the same Fusion session (R-25)

Do this **without restarting Fusion**.

- [ ] **K1** Stop 0.4.0, replace the `Push_To_GitHub` folder's contents with
      the candidate's, Run: the add-in starts; the Text Commands window (or
      the log) shows the new version; a push works (step 3 is that push).
- [ ] **A2** The Add-Ins list shows **Push to GitHub**; Run works; exactly
      **one** **Push to GitHub** button appears.
- [ ] **A3** Saved repositories from the previous version are all still
      listed.

## 3. First push with the candidate (existing repository)

Push the inch design to the repository from step 1 with F3D + STEP + STL.

- [ ] **C5** The dialog closes when the push starts; progress messages change
      and the result appears when it finishes.
- [ ] **H13** The background push's progress reaches the progress window
      (custom events fired from the worker thread arrive on Fusion's main
      thread).
- [ ] **H12** Exports are written (`exportManager.execute`).
- [ ] **C4** The success message names the branch and a short commit id.
- [ ] **C1** On GitHub, the design's files and `HISTORY.md` are in a folder
      named after the design; the old repository-root `CHANGELOG.md` is
      unchanged.
- [ ] **C6** The local repository folder is unchanged (`git status` the same
      as before the push).
- [ ] **A4** `.fusion_git_repos.json.v0-backup` now exists next to
      `.fusion_git_repos.json` in your home folder (first upgrade from 0.4.0
      or earlier only).

## 4. The dialog itself

- [ ] **H1** Opening the dialog several times, and changing Export Formats
      several times, never shows an error (input ids are reused after
      `deleteMe()`).
- [ ] **H2** The Format Settings table rebuilds correctly when formats
      change.
- [ ] **H3** The repository dropdown selects one item; Export Formats allows
      several.
- [ ] **H4** Choosing a repository fills in its saved settings without
      triggering extra questions (setting values from code doesn't fire
      input events).
- [ ] **H18** The Edit Repository and Remove Repository controls are laid out
      sensibly in the Repository group.

## 4a. The 0.7.0 dialog, history and links (S5)

For 0.7.0 and later. Assumptions 27–32 in `tests/fakes/README.md`.

- [ ] **U1** The OK button reads **Back up now** and is greyed out until
      "What changed?" is filled in; the line under the files says what is
      missing, and disappears once it's complete.
- [ ] **U2** "What changed?" is empty every time the dialog opens.
- [ ] **U3** **Icon:** the toolbar button shows the blue cube with the
      orange branch, legible in Fusion's light and dark themes, at 100 % and
      at a high display scale (150 % or more); the same icon appears in
      Utilities → Add-Ins → Scripts and Add-Ins. Record a screenshot.
- [ ] **U4** Move the button from the toolbar into the ADD-INS menu
      ("Move to menu"/unpin), then Stop and Run the add-in and restart
      Fusion: it stays in the menu (audit COMP-13).
- [ ] **U5** "Files to include" lists descriptive names ("STEP (.step): for
      other CAD programs" …); choosing STEP adds no settings row.
- [ ] **U6** The Design line shows the design's name and "Fusion version:
      vN"; after an unsaved edit it says "with unsaved changes" and that
      Fusion's own history doesn't include them until you save.
- [ ] **U7** "Saves to" changes when you pick another repository, set
      Advanced → Backup branch, or tick Separate branch per backup.
- [ ] **U8** **Running history:** with a repository set up in step 5 (or
      a new one), back up the same design twice: on GitHub, `main` has
      `designs/<design>/` with the files and a `HISTORY.md` listing both
      backups with their Fusion versions, and there are no
      `fusion-export/...` branches.
- [ ] **U9** Set Advanced → Backup branch to `fusion-backups` and back up:
      the branch appears on GitHub with the design's folder; `main` doesn't
      change.
- [ ] **U10** The repository saved by 0.4.0 (step 1) still makes a new
      `fusion-export/...` branch per backup, and Separate branch per backup
      is ticked for it.
- [ ] **U11** After a backup, **Yes** opens the design's folder on GitHub in
      the browser; after another, **No** says the link is on the clipboard,
      and pasting it into the browser opens the same folder.
- [ ] **U12** **Check My Setup** with a saved repository: a report with an
      OK line for Git (and its version), the sign-in helper and the folder,
      a GitHub sign-in window if Git Credential Manager needs one, and
      "GitHub accepted the sign-in…". Nothing is pushed. Fusion stays usable
      while it runs.
- [ ] **U13** With the network off, a backup fails with a message that starts
      "Couldn't reach GitHub." and has Git's own message under "Technical
      details". No dialog in this whole session shows a Python traceback.
- [ ] **U14** **Two saved repositories for one GitHub repository** (risk
      R-24): add the test repository again under a second name and folder.
      Back up a design called `Bracket` through the first, then a
      *different* design also called `Bracket` through the second: they
      land in `designs/Bracket/` and `designs/Bracket (2)/`, and the summary
      explains the second folder.
- [ ] **U15** *(if available)* On a computer, or Windows account, without
      Git: opening the dialog with no saved repository reports "Git was not
      found" with a download link before anything else.
- [ ] **U16** *(if available)* With branch protection on `main` (GitHub →
      Settings → Branches), a running-history backup fails with "…that
      branch is protected" and suggests a Backup branch.

## 5. New repository setup

Use a second private test repository, or the same one with a new local
folder.

- [ ] **B2** Pasting a URL with a token in it (`https://user:ghp_xxx@github.com/…`)
      is refused with an explanation.
- [ ] **B1** "Set up new…", paste the repository URL, leave **Repository Name
      blank**, accept the suggested folder, OK: setup succeeds.
- [ ] **F1** At the "This pushes your design to …" notice, answer **No**:
      "Push cancelled — nothing was pushed."; the dialog stays open.
- [ ] **H6** After that refused/cancelled push the dialog stays open
      (`executeFailed`).
- [ ] **B4** OK again: the notice appears before this first push to the
      repository; accept it; the first push succeeds. The next push to it
      shows no notice.
- [ ] **B3** On a computer where Git has no name/email (or temporarily
      without them): the add-in asks once; answering **No** to "all
      repositories" leaves `git config --global user.name` unset; the next
      push doesn't ask again.
- [ ] **H8** Cancelling the name or email prompt cancels the push
      (`inputBox`).
- [ ] **H7** Yes/No and Yes/No/Cancel questions behave as their buttons say.

## 6. Exports and design folders

- [ ] **C2** Rename the design in Fusion and push: it goes to the **same**
      folder.
- [ ] **H11** A saved design keeps its folder when renamed, and an unsaved
      design keeps it after its first save (`dataFile.id`).
- [ ] **C3** A different design with the same name goes to `Name (2)`.
- [ ] **J7** A design whose name has characters Windows doesn't allow
      (`Arm: v2/final?`) pushes to a folder and files with those characters
      replaced by `_`.
- [ ] **J3** **STL units:** in the inch design, model a 10 mm cube and push
      STL. Open the STL in a slicer or viewer: it is **10 mm** (not 0.39 or
      254). If your Fusion build shows a warning that STL units follow the
      design's units instead, record the Fusion build.
- [ ] **J4** **STL per body:** Format Settings → STL files → One file per
      body, with bodies in the root and inside a component (including two
      bodies with the same name). Each body is its own file, named
      `<design> - <component path> - <body>.stl`, and each is in the right
      **position** relative to the others when opened together.
- [ ] **J5** Hidden bodies are skipped in per-body mode, with a warning.
- [ ] **J6** **A failed export stops the push:** make an export fail (for
      example an empty design with STL chosen). The message starts "Nothing
      was pushed because these exports failed"; GitHub is unchanged and the
      dialog stays open.
- [ ] **J1** **Linked components:** insert the second design as a linked
      component, choose F3D and push: the add-in names the linked component
      and asks. **No** pushes nothing; **Yes** pushes and `HISTORY.md` has a
      "Note" line about linked components.
- [ ] **H17** Linked components are detected (`isReferencedComponent` across
      `allOccurrences`, including nested ones), and a broken link (for
      example a linked design you moved or deleted) doesn't crash the push.
- [ ] **J2** **Restore check (required for 1.0; risk R-06):** download that
      `.f3d` from GitHub and open it in Fusion (File → Open → Open from my
      computer). **Record whether the linked component's geometry is
      present.** This decides whether the warning's wording is right.

## 7. Background push and cancel

Use a large export (several formats, high STL refinement) or a slow network
so the push takes a while.

- [ ] **I1** During the push, Fusion stays usable: orbit the view, open a
      menu. Progress messages keep changing.
- [ ] **I4** Start a second push while one is running: refused with an
      explanation; the first completes normally.
- [ ] **I2** **Cancel** in the progress window before the push reaches
      GitHub: "nothing was pushed"; GitHub shows no new branch or commit.
- [ ] **H14** The progress window stays visible and **Cancel** works while
      the add-in is idle, including after a question hid and re-showed it
      (`wasCancelled`).
- [ ] **I3** Cancel just after GitHub accepted the push (hard to time; try a
      large export): the message says the export *did* reach GitHub, naming
      the branch.
- [ ] **I5** A question during the push (Branch Name set to an existing
      branch, which asks about reusing it) appears on top and the push
      continues after you answer.
- [ ] **H15** A question or message shown during a background push appears
      on top, not behind the progress window.
- [ ] **H9** The progress window hides for questions and comes back for the
      push; questions are never hidden behind it.
- [ ] **I6** Close the design's document during a push: the push finishes or
      fails cleanly; Fusion doesn't crash.

## 8. Stored token

- [ ] **D1** **Advanced → Manage Token… → Yes**: the Token field shows
      **dots**, not the token.
- [ ] **H5** The Token field shows dots (`isPassword`).
- [ ] **D2** Save Token: confirmed; "Use Stored Token" ticked; the field is
      empty.
- [ ] **D3** A push with the stored token succeeds.
- [ ] **R1** In the repository's local folder run
      `git config --local http.proxy http://127.0.0.1:9` and push with the
      stored token: refused before anything is sent, naming `http.proxy`.
      Then `git config --local --unset http.proxy`.
- [ ] **R2** Run `git config --local remote.origin.pushurl
      https://github.com/<you>/<another-repo>.git` and push with the stored
      token: refused ("would send the push to …"). Then
      `git config --local --unset remote.origin.pushurl`.
- [ ] **E1** **Edit Repository…** → rename → Save Changes: the dropdown shows
      the new name, and a stored token still works.
- [ ] **D4** Manage Token… → Replace, then → Delete: both work.

## 9. Edit, Remove and failures

- [ ] **E2** Edit → change the GitHub address → answer **No** to updating the
      local folder: the folder's Git remote is unchanged.
- [ ] **E3** Edit → change the address to a different server: "Use Stored
      Token" is turned off, with an explanation.
- [ ] **E4** **Remove Repository…** → confirm: the entry disappears; the
      local folder still exists; a stored token is kept unless you answered
      **Yes** to deleting it.
- [ ] **F2** Disconnect the network and push: a readable error within a few
      minutes; Fusion recovers.
- [ ] **G1** **Logging & Privacy → Open Log File…** opens the log; it
      contains no token (search it for the start of your token).
- [ ] **G2** **Clear Log** deletes it; **Privacy Policy…** opens PRIVACY.md
      in the browser.

## 10. Lifecycle in one session

- [ ] **I7** Start a push and Stop the add-in during it (Add-Ins → Stop):
      Fusion doesn't hang; Run again works and shows one button.
- [ ] **K4** Stop and Run five times: exactly one button each time; pushes
      work after the last Run.
- [ ] **A5** (Covered by K4; it needs at least three Stop/Run cycles.)
- [ ] **H10** Stop then Run doesn't create a second button (`addCommand` with
      an existing id).
- [ ] **K3** **Rollback:** Stop, put the 0.4.0 files back, Run: 0.4.0
      starts and works, in the same session. Then Stop, put the candidate
      back, Run: the candidate starts (repeats K1).
- [ ] **K6** **Duplicate install:** copy the add-in folder to a second name
      (for example `Push_To_GitHub_copy`) and Run it: it shows a warning
      that another copy is running and adds no second button. Keep the copy
      for step 12.
- [ ] **K7** The other add-ins you use keep working after these steps
      (nothing else is unloaded).

## 11. Synced folders

- [ ] **L1** Choose (or set up) a repository folder inside OneDrive (or
      Dropbox): an ℹ️ note says the folder is synced; pushing is still
      allowed. *(if available)*
- [ ] **L2** A folder outside any synced location shows no note.

## 12. Restart Fusion

1. With the duplicate copy from K6 still installed and **Run on Startup**
   ticked for both, **quit Fusion**.
2. While Fusion is closed, copy `.fusion_git_repos.json` to a safe place,
   then replace its contents with `{not json`.
3. Start Fusion.

- [ ] **K5** The candidate starts by itself, **Run on Startup** is still
      ticked, and there is one button.
- [ ] **A1** This is the upgrade from the previous release followed by a
      Fusion restart: the add-in works after it.
- [ ] **H16** The duplicate-install warning appears normally at startup (it
      is shown from `run()`). Then remove the copy (Stop it, untick Run on
      Startup, delete its folder).
- [ ] **F3** Open the dialog: a message names the `.corrupt-…` copy that was
      kept. Quit Fusion, put your saved settings file back, start Fusion
      again, and check the repositories are listed.

## 13. Community Store and macOS *(if available)*

- [ ] **K2** **Community Store update:** update from the previous release
      through the Store in a running Fusion: the Store reports the new
      version running; no rollback.
- [ ] **K8** **macOS Community Store update** (reported by DiegoV71 in #11):
      on a Mac, update from the previous release through the Store in a
      running Fusion, and record the Fusion build and result.
- [ ] **M1** Git is found when installed by Homebrew (`/opt/homebrew/bin/git`),
      the Xcode Command Line Tools, or the git-scm installer; record which.
- [ ] **M2** Browser sign-in through Git Credential Manager works, or record
      the exact message if it doesn't.
- [ ] **M3** Steps 3, 6, 7 and 10 behave as on Windows; record anything
      different, with the Fusion build.

## Coverage of the acceptance criteria

| Original section | Criteria | Checked in step |
|---|---|---|
| A. Install and upgrade | A1–A5 | 2 (A2, A3), 3 (A4), 10 (A5), 12 (A1) |
| B. New repository setup | B1–B4 | 5 |
| C. Pushing | C1–C6 | 3 (C1, C4–C6), 6 (C2, C3) |
| D. Stored token | D1–D4 | 8 |
| E. Edit and Remove | E1–E4 | 8 (E1), 9 (E2–E4) |
| F. Failures | F1–F3 | 5 (F1), 9 (F2), 12 (F3) |
| G. Logging and privacy | G1–G2 | 9 |
| H. Simulated behaviour | H1–H18 | 3 (H12, H13), 4 (H1–H4, H18), 5 (H6–H8), 6 (H11, H17), 7 (H9, H14, H15), 8 (H5), 10 (H10), 12 (H16) |
| I. Background push and cancel | I1–I7 | 7 (I1–I6), 10 (I7) |
| J. Export integrity | J1–J7 | 6 |
| K. Updates, restarts, duplicates | K1–K8 | 2 (K1), 10 (K3, K4, K6, K7), 12 (K5), 13 (K2, K8) |
| L. Synced folders | L1–L2 | 11 |
| M. macOS | M1–M3 | 13 |
| R-21 live checks | R1–R2 | 8 |
| 0.7.0 dialog, history, links, icon (S5) | U1–U16 | 4a (U8 after step 5; U13 with step 9's network test) |

