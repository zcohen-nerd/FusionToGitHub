# Manual Fusion checklist

Run this in **real Fusion on Windows** before publishing a release (CONTRIBUTING
→ Releasing, step 5). The automated tests run the dialog against *simulated*
Fusion objects (`tests/fakes/adsk`); this list covers what only real Fusion can
show. About 20 minutes. macOS is Experimental: run it there too if you can, and
report the results in an issue.

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
- [ ] Fusion keeps repainting during the push (progress messages change).
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
- [ ] Exports are written (`exportManager.execute`), and Fusion keeps
      repainting during the push (`adsk.doEvents()`).
- [ ] The Edit Repository and Remove Repository controls are laid out
      sensibly in the Repository group.
