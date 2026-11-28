# Privacy

FusionToGitHub ("the add-in") is an open-source Autodesk Fusion add-in that
copies your designs to a Git repository you choose, usually on GitHub. This page
explains what it stores on your computer, what it sends and to whom, and how to
delete it.

**In short:** the add-in has no server and collects nothing. It sends your
exported design files, your commit note and your Git name and email to the
repository you configured, and nowhere else. Whether anyone else can see them
depends on that repository's visibility.

## What the add-in does not do

- **No telemetry, analytics or tracking.** The add-in makes no network
  connections of its own. It only runs `git`, which connects to the repository
  address you configured.
- **No account.** It has no server and no sign-up; the maintainer receives
  nothing from you.
- **No GitHub API calls.** It never reads your GitHub account, other
  repositories, or anything else on GitHub.

The only other connection is your web browser opening this page when you click
**Privacy Policy…**.

## What is sent, and to whom

When you click **Back up now** in the **Push to GitHub** dialog, `git` sends these to the
repository address you configured (for example `github.com/you/designs`):

| Data | Details |
|------|---------|
| **Your exported design files** | The formats you ticked: F3D (the complete Fusion design, including its timeline, sketches and history), STEP, STL, IGES, SAT. For a design with linked components (components inserted from other designs), the Fusion file is an `.f3z` archive, which can include **the linked designs' content too**: check that you may publish them. `HISTORY.md` then also names the linked components. |
| **Your commit note** | The message you type, plus the design name. |
| **Your Git name and email** | Git records them as the author of every commit. Use GitHub's private "noreply" address if you don't want your email published: GitHub → *Settings → Emails → Keep my email addresses private*, then use the `…@users.noreply.github.com` address it shows. |
| **Date, time and time zone** | Git stores when each commit was made, with your time zone offset. |
| **A history file per design** | A `HISTORY.md` in the design's folder listing each backup: date and time, design name, branch, your note, the file names, and which Fusion version of the design it was (for example "v12 with unsaved changes"). Since 0.7.0 it also carries a hidden marker: a 16-character hash of the design's Fusion document id (not the id itself), so the add-in can tell designs with the same name apart. The marker is the same in every repository the design is backed up to, so someone who can see two such repositories can tell they hold the same design (not which design it is). Versions before 0.6.0 kept one `CHANGELOG.md` for the whole repository instead. |
| **Branch names** | The branch backups go to: the repository's main branch or a backup branch you chose, or, with "Separate branch per backup", a new branch such as `fusion-export/Bracket-20261127-101500`. |

The receiving service (normally **GitHub, Inc.**) handles this data under its
own terms and privacy statement. **If the repository is public, anyone can see
and download everything you push**, and copies can remain in forks and clones
even after you delete them. Before the first push to each repository, the
add-in reminds you of this and asks you to confirm. Use a private repository
for designs you don't want to publish.

If you sign in through Git Credential Manager, the sign-in happens between Git,
your browser and GitHub; the add-in doesn't see it.

**Check My Setup** asks the repository's server which branches it has, with
the same sign-in a backup uses. Nothing is sent to the repository and nothing
is changed. **Copy Link** uses your computer's own clipboard tool; **Open on
GitHub** opens the link in your browser.

## What is stored on your computer

| What | Where | Kept until |
|------|-------|-----------|
| Saved repository settings: folder, address, formats, templates, options | `.fusion_git_repos.json` in your home folder | You delete it |
| Activity log: what the add-in did, with folder paths, repository addresses, design names and Git messages. Passwords and tokens are removed before anything is written. | `.PushToGitHub_AddIn_Data/` in your home folder: up to four files of 1 MB each; the oldest is overwritten | You clear it (**Help & Privacy → Clear Log**) |
| Optional stored token (Windows only, if you use **Manage Token…**) | Windows Credential Manager, entry `FusionToGitHub::<repository name>` | You delete it (**Manage Token… → Delete**) |
| Your Git name and email, if Git didn't have them yet | With that repository's saved settings (above); in your global Git configuration (`~/.gitconfig`) only if you chose "all repositories" | You change or remove it |
| Exported files during a push | A temporary folder | Deleted automatically when the push ends |
| The stored token, while one Git command that needs it runs | A file in `%LOCALAPPDATA%\PushToGitHub\credentials` (Windows; if that folder can't be used, `.PushToGitHub_AddIn_Data\credentials` in your home folder) | Overwritten and deleted when that command ends (seconds); a leftover from a crash is deleted by a later push after an hour |
| The local repository folder you chose during setup | That folder | You delete it. (Pushing never changes it.) |

On macOS the settings file and logs are readable only by your user account. On
Windows they are in your user profile, which is private to you by default.

## Deleting your data

On your computer:

1. **Logs:** in the dialog, **Help & Privacy → Clear Log**, or delete the
   `.PushToGitHub_AddIn_Data` folder in your home folder.
2. **Stored token:** **Advanced → Manage Token… → No (Delete it)**. Then revoke
   the token on GitHub (*Settings → Developer settings → Personal access
   tokens*).
3. **Settings:** delete `.fusion_git_repos.json` in your home folder.
4. **The add-in:** delete the `Push_To_GitHub` folder from Fusion's `AddIns`
   folder.

On GitHub: pushed commits stay in the repository's history. Deleting the files
in a later commit doesn't remove earlier versions. To remove everything, delete
the repository (*Settings → Danger zone*); copies in forks or other people's
clones are outside your control. GitHub's documentation explains how to remove
sensitive data from a repository's history.

## Changes and contact

Changes to this policy are listed in the [CHANGELOG](CHANGELOG.md). Questions:
open an [issue](https://github.com/zcohen-nerd/FusionToGitHub/issues), or see
[SECURITY.md](SECURITY.md) for anything sensitive.

*Last updated: 2026-11-28 (version 0.8.0, in development; the current release is 0.4.0, which doesn't have the design marker, Check My Setup or the per-command credential file).*
