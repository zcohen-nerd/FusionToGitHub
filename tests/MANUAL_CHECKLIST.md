# Manual Fusion checklist

Run this in **real Fusion on Windows** before publishing a release (CONTRIBUTING
→ Releasing, step 5). The automated tests run the dialog against *simulated*
Fusion objects (`tests/fakes/adsk`); this list covers what only real Fusion can
show. About 60 minutes (sections I–K, new in 0.6.0, take about half).
macOS is Experimental: run it there too if you can, and report the results in
an issue. **A release is not published until every applicable item passes**
or its failure is recorded with a maintainer decision.

Use a **private test repository** and a throwaway design. Tick each line, note
anything odd, and attach the filled-in list to the release.

| Item | Value |
|---|---|
| Add-in version | |
| Fusion build (Help → About) | |
| Windows version | |
| Date, tester | |

## A. Install and upgrade

- [ ] Upgrade from the previous release: stop the add-in, replace the
      `Push_To_GitHub` folder with the new ZIP's, restart Fusion.
- [ ] The Add-Ins list shows **Push to GitHub**; Run works; exactly **one**
      **Push to GitHub** button appears.
- [ ] Saved repositories from the previous version are all still listed.
- [ ] After the first push, `.fusion_git_repos.json.v0-backup` exists next to
      `.fusion_git_repos.json` in your home folder (first upgrade from 0.4.0
      or earlier only).
- [ ] Stop and Run the add-in three times: still exactly one button.

## B. New repository setup

- [ ] "Set up new…", paste the repository URL, leave **Repository Name
      blank**, accept the suggested folder, OK: setup and first push succeed.
- [ ] Pasting a URL with a token in it (`https://user:ghp_xxx@github.com/…`)
      is refused with an explanation.
- [ ] On a computer where Git has no name/email: the add-in asks once;
      answering **No** to "all repositories" leaves `git config --global
      user.name` unset; the next push doesn't ask again.
- [ ] The "This pushes your design to …" notice appears before the first push
      to the repository, and not on the second.

## C. Pushing

- [ ] On GitHub, the design's files and `HISTORY.md` are in a folder named
      after the design; an old repository-root `CHANGELOG.md` is unchanged.
- [ ] Rename the design in Fusion and push: it goes to the **same** folder.
- [ ] A different design with the same name goes to `Name (2)`.
- [ ] The success message names the branch and a short commit id.
- [ ] The dialog closes when the push starts; progress messages change and
      the result appears when it finishes.
- [ ] The local repository folder is unchanged (`git status` the same as
      before the push).

## D. Stored token

- [ ] **Advanced → Manage Token… → Yes**: the Token field shows **dots**, not
      the token.
- [ ] Save Token: confirmed; "Use Stored Token" ticked; the field is empty.
- [ ] A push with the stored token succeeds.
- [ ] Manage Token… → Replace, then → Delete: both work.

## E. Edit and Remove

- [ ] **Edit Repository…** → rename → Save Changes: the dropdown shows the new
      name, and a stored token still works.
- [ ] Edit → change the GitHub address → answer **No** to updating the local
      folder: the folder's Git remote is unchanged.
- [ ] Edit → change the address to a different server: "Use Stored Token" is
      turned off, with an explanation.
- [ ] **Remove Repository…** → confirm: the entry disappears; the local folder
      still exists; a stored token is kept unless you answered **Yes** to
      deleting it.

## F. Failures

- [ ] Declining the publication notice: "Push cancelled — nothing was
      pushed."; the dialog stays open.
- [ ] Disconnect the network and push: a readable error within a few minutes;
      Fusion recovers.
- [ ] With Fusion closed, put `{not json` in `.fusion_git_repos.json`, start
      Fusion and open the dialog: a message names the `.corrupt-…` copy that
      was kept. (Restore your settings from that copy afterwards.)

## G. Logging and privacy

- [ ] **Logging & Privacy → Open Log File…** opens the log; it contains no
      token.
- [ ] **Clear Log** deletes it; **Privacy Policy…** opens PRIVACY.md in the
      browser.

## H. Simulated behaviour to confirm

The dialog tests run against stand-ins (`tests/fakes/adsk`, see its README)
that assume the following about Fusion. Confirm each by using the dialog:

- [ ] Opening the dialog several times, and changing Export Formats several
      times, never shows an error (input ids are reused after `deleteMe()`).
- [ ] The Format Settings table rebuilds correctly when formats change.
- [ ] The repository dropdown selects one item; Export Formats allows several.
- [ ] Choosing a repository fills in its saved settings without triggering
      extra questions (setting values from code doesn't fire input events).
- [ ] The Token field shows dots (`isPassword`).
- [ ] After a refused or cancelled push, the dialog stays open
      (`executeFailed`).
- [ ] Yes/No and Yes/No/Cancel questions behave as their buttons say.
- [ ] Cancelling the name or email prompt cancels the push (`inputBox`).
- [ ] The progress window hides for questions and comes back for the push;
      questions are never hidden behind it.
- [ ] Stop then Run doesn't create a second button (`addCommand` with an
      existing id).
- [ ] A saved design keeps its folder when renamed, and an unsaved design
      keeps it after its first save (`dataFile.id`).
- [ ] Exports are written (`exportManager.execute`).
- [ ] The background push's progress reaches the progress window (custom
      events fired from the worker thread arrive on Fusion's main thread).
- [ ] The progress window stays visible and **Cancel** works while the
      add-in is idle, including after a question hid and re-showed it
      (`wasCancelled`).
- [ ] A question or message shown during a background push appears on top,
      not behind the progress window.
- [ ] The duplicate-install warning appears normally at Fusion startup (it
      is shown from `run()`).
- [ ] Linked components are detected (`isReferencedComponent` across
      `allOccurrences`, including nested ones), and a broken link doesn't
      crash the push.
- [ ] The Edit Repository and Remove Repository controls are laid out
      sensibly in the Repository group.

## I. Background push and cancel (new in 0.6.0)

The Git part of a push now runs on a background thread; Fusion is only
touched on its main thread, through a custom event.

- [ ] During a push to a slow connection (or a large export), Fusion stays
      usable: orbit the view, open a menu. Progress messages keep changing.
- [ ] **Cancel** in the progress window before the push reaches GitHub:
      "nothing was pushed"; GitHub shows no new branch or commit.
- [ ] Cancel just after GitHub accepted the push (hard to time; try a large
      export): the message says the export *did* reach GitHub, naming the
      branch.
- [ ] Start a second push while one is running: refused with an explanation;
      the first completes normally.
- [ ] A question during the push (for example reusing an existing branch)
      appears on top and the push continues after you answer.
- [ ] Close the design's document during a push: the push finishes or fails
      cleanly; Fusion doesn't crash.
- [ ] Stop the add-in during a push (Add-Ins → Stop): Fusion doesn't hang;
      Run again works and shows one button.

## J. Export integrity (new in 0.6.0)

- [ ] **Linked components:** insert another design as a linked component,
      choose F3D and push: the add-in names the linked component and asks.
      **No** pushes nothing; **Yes** pushes and `HISTORY.md` has a "Note"
      line about linked components.
- [ ] Download that `.f3d` from GitHub and open it in Fusion (File → Open →
      Open from my computer). Record whether the linked component's
      geometry is present. (This decides whether the warning is justified.)
- [ ] **STL units:** in a design whose units are **inches**, model a 10 mm
      cube and push STL. Open the STL in a slicer or viewer: it is **10 mm**
      (not 0.39 or 254). If your Fusion build shows a warning that STL units
      follow the design's units instead, record the Fusion build.
- [ ] **STL per body:** Format Settings → STL files → One file per body, with
      bodies in the root and inside a component (including two bodies with
      the same name). Each body is its own file, named
      `<design> - <component path> - <body>.stl`, and each is in the right
      **position** relative to the others when opened together.
- [ ] Hidden bodies are skipped in per-body mode, with a warning.
- [ ] **A failed export stops the push:** for example choose a format and
      make the export fail (an empty design for STL). The message starts
      "Nothing was pushed because these exports failed"; GitHub is
      unchanged and the dialog stays open.
- [ ] A design whose name has characters Windows doesn't allow
      (`Arm: v2/final?`) pushes to a folder and files with those characters
      replaced by `_`.

## K. Updates, restarts and duplicate installs (new in 0.6.0)

Same-process updates failed before 0.6.0 because modules from the previous
version stayed loaded (risk R-25, reported by DiegoV71). Run each in **one
Fusion session** without restarting Fusion, unless the step says so.

- [ ] **Stop → update → Run:** with the previous release running, Stop it,
      replace the `Push_To_GitHub` folder with this release's files, Run:
      the add-in starts; the Text Commands window (or the log) shows the new
      version; a push works.
- [ ] **Community Store update** (if the Store is installed): update from the
      previous release in a running Fusion: the Store reports the new
      version running; no rollback.
- [ ] **Rollback / downgrade:** Stop, put the previous release's folder back,
      Run: the previous version starts and works, in the same session.
- [ ] **Restart:** Stop and Run five times: exactly one button each time;
      pushes work after the last Run.
- [ ] **Run on Startup:** with Run on Startup ticked, update (as above), then
      restart Fusion: the add-in starts by itself, Run on Startup is still
      ticked, one button.
- [ ] **Duplicate install:** copy the add-in folder to a second name (for
      example `Push_To_GitHub_copy`) and Run both: the second shows a warning
      that another copy is running and adds no second button. Remove the
      copy afterwards.
- [ ] Other add-ins you use keep working after these steps (nothing else is
      unloaded).
- [ ] **macOS Community Store update** (reported by DiegoV71 in #11): if a
      macOS tester is available, update from the previous release through
      the Store in a running Fusion and record the Fusion build and result.

## L. Synced folders (new in 0.6.0)

- [ ] Choose (or set up) a repository folder inside OneDrive (or Dropbox):
      an ℹ️ note says the folder is synced; pushing is still allowed.
- [ ] A folder outside any synced location shows no note.

## M. macOS (Experimental; only if you have a Mac)

- [ ] Git is found when installed by Homebrew (`/opt/homebrew/bin/git`), the
      Xcode Command Line Tools, or the git-scm installer; record which.
- [ ] Browser sign-in through Git Credential Manager works, or record the
      exact message if it doesn't.
- [ ] Sections C, I, J and K behave as on Windows; record anything
      different, with the Fusion build.
