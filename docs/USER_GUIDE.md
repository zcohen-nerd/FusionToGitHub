# User guide

Everything in the **Push to GitHub** dialog, and what happens when you click
**Back up now**. To install the add-in, see the [installation guide](INSTALL.md);
to get a version back, the [backup and restore guide](RESTORE.md).

- [The dialog at a glance](#the-dialog-at-a-glance)
- [Design](#design)
- [Repository](#repository)
- [What changed?](#what-changed)
- [Files to include](#files-to-include)
- [Advanced](#advanced)
- [Help & Privacy](#help--privacy)
- [What happens when you click Back up now](#what-happens-when-you-click-back-up-now)
- [Where backups go](#where-backups-go)
- [Stored tokens (Windows)](#stored-tokens-windows)
- [Several repositories, several computers](#several-repositories-several-computers)
- [Glossary](#glossary)

## The dialog at a glance

| Part | Shown | What it's for |
|---|---|---|
| Design | Always | Which design is backed up, and its Fusion version |
| Repository | Always | Where on GitHub it goes; set up, edit or remove repositories; Check My Setup |
| What changed? | Always | Your note for this backup (required) |
| Files to include | Always | Which file types to export |
| Advanced | Collapsed | How backups are recorded in Git, folder layout, stored token |
| Help & Privacy | Collapsed | Privacy policy, log file |

**Back up now** stays greyed out until everything a backup needs is filled in.
The line under *Files to include* says what is missing, for example *"Before
backing up: Describe what changed (What changed?)."*

## Design

Shows the open design's name and its Fusion version, for example *Bracket
(Fusion version: v12)*. If it has unsaved changes, it says so: the backup
includes them, but Fusion's own version history only does once you save. A
design that was never saved shows *not saved yet*. The version is recorded in
the design's `HISTORY.md`.

If no design is open (for example a drawing or the Manufacture workspace),
open the design you want to back up and click the button again.

## Repository

**Repository** lists your saved repositories, with **Set up a new GitHub
repository…** at the end. The add-in starts on the one you used last.

### Setting up a new repository

1. Create the repository on github.com first (see the [README](../README.md#your-first-backup-5-minutes)).
2. **GitHub address:** paste its address from the browser. Any of these work:
   `https://github.com/you/designs`, `github.com/you/designs`,
   `https://github.com/you/designs.git`, `git@github.com:you/designs.git`. The
   line below shows the address that will be used. An address with a password
   or token in it is refused; store a token with [Manage Token…](#stored-tokens-windows) instead.
3. **Name in this list:** optional. It's only how the repository is listed in
   this add-in. Left blank, it's taken from the address.
4. **Local folder:** where Git keeps its copy of the repository on this
   computer. The suggested folder is `FusionGitRepos/<name>` in your home
   folder; **Choose folder…** picks another. An existing empty folder, or a
   folder that already holds a copy of that repository, is fine. A folder
   inside OneDrive, Dropbox, iCloud Drive or Google Drive works, but gets a
   note: sync apps can lock or duplicate Git's files.

The repository is set up when you click **Back up now**, and the first backup
follows straight away. New repositories keep [one running history](#where-backups-go).

### Saves to

Shows where this backup will go, as *branch › folder*: for example *the
repository's main branch › designs/Bracket/*.

### Edit Repository…

Change a saved repository's name in this list, its GitHub address or its local
folder; click **Save Changes**. Pressing **Edit Repository…** again cancels.

- When you change the address, the add-in asks whether to point the local
  folder's Git settings at the new address too. **No** keeps the folder
  connected to its current address.
- Changing to a folder or a server the stored token wasn't saved for turns
  **Use stored token** off, so a token is never sent somewhere it wasn't
  stored for.
- A changed address shows the publication notice again before the next backup.

### Remove Repository…

Forgets a saved repository in this add-in. The local folder, the repository on
GitHub and every backup in it are **not touched**; you can add it again later.
If a token is stored for it, you're asked separately whether to delete it too.

### Check My Setup…

Checks everything a backup needs, without backing anything up:

- Git: whether it's installed, where, and its version (2.30 or newer is
  recommended).
- Your name and email for backups.
- How Git signs in to GitHub: Git Credential Manager, a stored token, or
  nothing.
- With a saved repository selected: its local folder, its connection to the
  address you saved, whether the folder is inside a sync app, and the stored
  token's conditions.
- Then a **connection test**: Git asks GitHub which branches the repository
  has, with the same sign-in a backup uses. A GitHub sign-in window may open.
  Nothing is sent or changed. Fusion stays usable meanwhile.

Each result is marked **[OK]**, **[Check]**, **[Problem]** or **[Note]**, with
what to do next. The first time you open the dialog, before any repository is
saved, anything that would stop a first backup (such as Git missing) is shown
straight away.

## What changed?

Required, and empty every time: a few words about this version, such as
*holes widened to 5 mm*. It becomes the commit's title on GitHub (as
*Bracket: holes widened to 5 mm* for repositories set up with 0.7.0 or later;
see [Commit message format](#commit-message-format)) and appears in the
design's `HISTORY.md`.

## Files to include

Pick one or more:

| File | Use it for |
|---|---|
| **Fusion design (.f3d)** | Restoring in Fusion: the full editable design with its timeline. **The one to restore from.** |
| **STEP (.step)** | Opening in other CAD programs (SolidWorks, Inventor, FreeCAD, …) |
| **IGES (.igs)** | Older CAD programs that don't read STEP |
| **SAT (.sat)** | Programs based on the ACIS modelling kernel |
| **STL (.stl, millimetres)** | 3D printing and mesh tools |

The default is Fusion design + STEP + STL.

**Format settings** (shown for STL):
- **STL** (mesh refinement): *High (refined mesh)* for smooth, larger files, *Medium*, or *Low (fast)* for smaller ones.
- **STL files:** *One file* for the whole design, or *One file per body*, named
  like `Bracket - Arm 1 - Pin.stl`. Hidden bodies are left out, with a note.

STL files are written in millimetres on recent Fusion versions; on older ones
they use the design's units, and the summary says so.

**All or nothing:** every file you pick must export and pass basic checks (it
exists, isn't empty, is the right kind of file, is under 100 MB). If one fails,
nothing is sent and the history isn't changed. These checks don't prove a file
opens in other software.

## Advanced

### Separate branch per backup

**Off** (recommended, and the default for repositories set up with 0.7.0 or
later): every backup is added to one running history. **On**: each backup goes
to a new branch of its own, named by the **Branch name template** (as versions
before 0.7.0 did; repositories set up with those versions have it ticked). See
[Where backups go](#where-backups-go).

### Backup branch

With one running history: blank adds backups to the repository's main branch.
A name such as `fusion-backups` keeps them on a branch of their own instead; it
is created, from the main branch, on the first backup. Useful when other work
lives on `main`, or `main` is protected.

### Branch name template and Use this branch instead

With separate branches only. The template names each new branch (default
`fusion-export/{filename}-{timestamp}`). **Use this branch instead** sends this
one backup to a branch you name; if it already exists, the add-in asks before
adding to it (and warns specially if it's the repository's main branch).

### Design folders go in

The folder that holds one folder per design. Default `designs`, giving
`designs/Bracket/`. Blank puts the design folders at the top level of the
repository. `{filename}` (the design's name) and `{timestamp}` may be used for
unusual layouts.

### Commit message format

How each commit is titled. New repositories use `{filename}: {message}`.

| Placeholder | Becomes |
|---|---|
| `{message}` | What you typed in *What changed?* |
| `{filename}` | The design's name |
| `{timestamp}` | Date and time, `YYYYMMDD-HHMMSS` |
| `{branch}` | The branch the backup goes to |

A format without `{message}` (saved by a version before 0.7.0) uses what you
typed as the whole message.

### Use stored token and Manage Token…

Windows only. See [Stored tokens](#stored-tokens-windows).

## Help & Privacy

- **Privacy Policy…** opens [PRIVACY.md](../PRIVACY.md) on GitHub.
- **Open Log File…** opens the add-in's log, in `.PushToGitHub_AddIn_Data/` in
  your home folder. Passwords and tokens are removed before anything is written.
- **Clear Log** deletes the log files.
- **Log detail:** ERROR, WARNING, INFO (normal) or DEBUG (for investigating a
  problem).

## What happens when you click Back up now

1. **Setup**, for a new repository: the local folder is cloned or connected to
   the address.
2. **Export**, with a progress window. If any file fails its checks, nothing is
   sent.
3. **Questions**, only when they apply:
   - **Linked components:** if the design contains components linked from
     other designs, the add-in names them and asks whether to back up anyway.
     The `.f3d` may not include them (see [restore](RESTORE.md#designs-with-linked-components)).
   - **Publication notice**, once per repository: the backup is published to
     that repository, and a public repository is visible to everyone.
   - **Name and email**, once, if Git doesn't have them. They are saved for
     that repository in this add-in. Your global Git settings are changed only
     if you choose "all repositories".
   - **Large files:** files over 50 MB need a Yes. Files of 100 MB or more are
     refused (GitHub's limit).
4. **The dialog closes and the backup is sent in the background.** Fusion stays
   usable. The progress window shows each step, and **Cancel** stops it.
5. **Summary:**
   - **Success:** the repository, *branch › folder*, the commit, the Fusion
     version and the files. Then: **Yes** opens the design's folder on GitHub in
     your browser, **No** copies the link, **Cancel** closes.
   - **Cancelled:** the message says which of these happened: nothing was
     sent; GitHub had already received the backup (no need to back up again);
     only an empty repository's first commit was sent; or it couldn't tell
     (look at the repository before backing up again).
   - **Failed:** a plain first line, what to do next, and Git's own message
     under *Technical details*. A failed backup normally leaves GitHub
     unchanged; if the message asks you to check the repository, do so before
     backing up again.

The add-in never changes your files or branches in the local folder, never
deletes or overwrites a backup, and never force-pushes (replaces what is on
GitHub). If someone else added to the branch meanwhile, the backup is rebuilt
on top of their changes.

## Where backups go

**One running history (default for new repositories).** Every backup is a new
commit on one branch (the repository's main branch, or your *Backup branch*),
in the design's folder:

```
designs/
  Bracket/
    Bracket.f3d
    Bracket.step
    Bracket.stl
    HISTORY.md
  Gearbox/
    …
```

The folder always holds the newest version; GitHub's **History** shows every
earlier one.

**Separate branch per backup.** Each backup is a new branch such as
`fusion-export/Bracket-20261128-143022`, starting from the main branch, with the
design's folder inside it. To see one, pick it in GitHub's branch list.

**Design folders.** A design gets its folder the first time it's backed up,
named after it, and keeps that folder when you rename the design in Fusion. A
different design with the same name gets `Bracket (2)`. Names are made safe for
Windows, macOS and GitHub (characters Windows doesn't allow become `_`).

**HISTORY.md** lists every backup of the design, newest first:

```
## 2026-11-28 14:30:22 - Bracket
- **Branch:** `main`
- **Commit Message:** "Bracket: holes widened to 5 mm"
- **Fusion version:** v12
- **Files Updated:**
  - `designs/Bracket/Bracket.f3d`
  - `designs/Bracket/Bracket.step`
```

It also carries a hidden marker line, so the add-in can tell designs with the
same name apart (see [PRIVACY.md](../PRIVACY.md)). Repositories used with
versions before 0.6.0 also have one `CHANGELOG.md` at the top level; it is left
as it was, and each design's `HISTORY.md` points to it.

**Empty repositories.** If the repository on GitHub is completely empty, the
first backup also adds a small first commit to `main` with a `.gitattributes`
file, which stops Git from altering CAD files.

## Stored tokens (Windows)

You normally don't need one: Git Credential Manager opens a GitHub sign-in
window the first time and remembers you. A stored token is for when that
doesn't suit, for example an account with single sign-on that GCM can't use.

1. On GitHub: **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**. Choose **Only select
   repositories** (just this one), **Contents: Read and write**, nothing else,
   and the shortest practical expiry.
2. In the dialog, select the repository, open **Advanced**, click **Manage
   Token…** and answer **Yes** to add one.
3. Paste the token into **Token** (it shows dots), optionally a **Token
   username**, and click **Save Token**. **Use stored token** is then ticked.

The token is kept in Windows Credential Manager, bound to the repository's
server, and only ever sent to that repository over https.
[SECURITY.md](../SECURITY.md) describes every protection and its limits.
**Manage Token…** on a repository that has one lets you replace or delete it.
Deleting it here doesn't revoke it on GitHub; do that in GitHub's settings.

## Several repositories, several computers

You can save as many repositories as you like and pick one each time. Two
saved entries for the same GitHub repository, or the same repository used on
two computers, work: each design keeps its own folder, because the add-in checks
the folders already on GitHub before each backup. For several people sharing
one repository, see [Teams](TEAMS.md).

## Glossary

| Word | Meaning |
|---|---|
| **Repository** | A project on GitHub that keeps every version of its files |
| **Commit** | One saved version, with a note about what changed. Each backup is one commit. |
| **Branch** | A line of commits. Backups go on the repository's main branch unless you choose otherwise. |
| **Push** | Sending commits to GitHub. The add-in does this when you click Back up now. |
| **Local folder** | Git's copy of the repository on your computer. The add-in uses it but never changes your files in it. |
| **Token** | A password-like key from GitHub that lets a program write to a repository |
| **Git Credential Manager (GCM)** | The program, installed with Git, that signs Git in to GitHub through your browser |
| **Force-push** | Replacing what is on GitHub with something else, which can lose work. The add-in never does it. |
| **Clone** | Git's copy of a repository on your computer (the local folder) |
| **origin/main** | In the local folder, Git's record of the `main` branch on GitHub as of the last backup or download |
| **Pull request** | A GitHub request to bring the changes on one branch into another, for someone to review first |
