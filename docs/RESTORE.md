# Backing up and getting a version back

A backup is only useful if you can get the design back. This guide covers what
a backup contains, how to find the version you want, and how to open it in
Fusion again. **Try it once now, with a design that doesn't matter**, so you
know it works before you need it.

- [What a backup contains](#what-a-backup-contains)
- [Find the version you want](#find-the-version-you-want)
- [Download it](#download-it)
- [Open it in Fusion](#open-it-in-fusion)
- [Designs with linked components](#designs-with-linked-components)
- [If GitHub isn't available](#if-github-isnt-available)
- [With Git on the command line](#with-git-on-the-command-line)

## What a backup contains

Each time you click **Back up now**, one commit is added to your repository with:

| | |
|---|---|
| **The files you chose** | `Bracket.f3d` (the editable Fusion design, with its timeline), `Bracket.step`, `Bracket.stl`, … in the design's folder, for example `designs/Bracket/` |
| **HISTORY.md** | A new entry at the top: date and time, your note, the branch, the files, and the Fusion version of the design (for example *v12 with unsaved changes*) |
| **The commit** | Your note as its title, your Git name and email, and the time |

**Not included:**
- Drawings, which are separate Fusion documents.
- Your Fusion project structure and comments.
- Components linked from *other* designs (see [below](#designs-with-linked-components)).
- Anything else in the Fusion document beyond what Fusion's `.f3d` export writes. Whether Manufacture (CAM) setups are in the `.f3d` depends on Fusion's export and hasn't been checked.

The backup is a copy of the design *as exported*. Fusion's own version history
in Autodesk's cloud is separate and unaffected; keep both.

## Find the version you want

*The menus and buttons named here (in Fusion and on GitHub) are as their makers describe them; they haven't yet been checked step by step for this guide (live check W2). If something is named differently, look for the nearest equivalent and [tell us](../SUPPORT.md).*

Open your repository on github.com, then the design's folder
(`designs/<design name>/`; repositories set up before 0.7.0 may have it at the
top level).

- **HISTORY.md** lists every backup of the design, newest first, with your
  notes and Fusion versions. It's the quickest way to find the one you want
  ("the version before I changed the holes").
- **A file's History:** open a file, such as `Bracket.f3d`, and click
  **History**. Every backup that changed it is listed with its note and date.
- **Separate branches per backup** (repositories set up before 0.7.0, or with
  that option ticked): each backup is a branch such as
  `fusion-export/Bracket-20261128-143022`. Click the branch list (it shows
  `main`), click **View all branches**, and open the one you want.

## Download it

**One file at a chosen version:**
1. Open the file, click **History**, and click the backup you want. GitHub
   shows that commit's changes.
2. At the top right of the file in that commit, click **⋯ → View file**.
3. Click **Download raw file** (the download icon).

**The whole design folder at a chosen version:**
1. In the file's **History**, click the **<>** (*Browse repository at this
   point*) button next to the backup you want.
2. Click **Code → Download ZIP**. The ZIP contains the whole repository as it
   was then; the design's files are in its folder.

**The newest version:** open the file on the repository's main page and click
**Download raw file**.

## Open it in Fusion

*The menus and buttons named here (in Fusion and on GitHub) are as their makers describe them; they haven't yet been checked step by step for this guide (live check W2). If something is named differently, look for the nearest equivalent and [tell us](../SUPPORT.md).*

**A Fusion design (`.f3d`):**
1. In Fusion, choose **File → Open**, then **Open from my computer…**, and pick
   the downloaded `.f3d`. Or, in the **Data Panel**, choose a project and click
   **Upload**.
2. Fusion should upload it as a **new design** in the current project, with
   its timeline, sketches and parameters, leaving your existing design and its
   Fusion version history unchanged. (Expected from how Fusion handles
   uploads; confirmed for this guide by live check W2.)
3. Rename it if you like, for example *Bracket (restored v12)*.

**STEP, IGES or SAT:** open them the same way. They contain the shape but not
Fusion's timeline: you get solid bodies, not the features that made them.

**STL:** in a design, use **Insert → Insert Mesh**. STL files are in
millimetres when the Fusion version that made them allowed it; otherwise they
are in the design's units, and that backup's summary said "STL files have no
units". Check the scale when inserting.

**In other CAD programs:** open the STEP file (or IGES or SAT) with the
program's own import command.

## Designs with linked components

If the design contains components inserted from *other* Fusion designs (linked
components, shown with a link icon in the browser), its `.f3d` backup **may not
restore on its own**. Fusion's API documents only the `.f3d` archive; Fusion's
own archive format for designs with references (`.f3z`) has no documented API
for add-ins.
Restoring such a backup hasn't been verified yet. The add-in asks before backing
up such a design and records the limitation in `HISTORY.md`.

To be safe:
- Keep the linked designs in Fusion. They are separate documents in your
  project, and Fusion keeps their versions.
- Back up the linked designs too: open each one and click **Push to GitHub**.
- Include **STEP**: it contains the complete geometry, including the linked
  components, as plain bodies.
- When you restore, open the `.f3d` and check that every component is there.
  If some are missing, insert them from the linked designs' own backups, or
  use the STEP file.

## If GitHub isn't available

The local folder the add-in uses (shown when you set up the repository; by
default `FusionGitRepos/<name>` in your home folder) has Git's copy of every
backup made **from this computer**, up to its most recent backup. The add-in
doesn't put the files in that folder itself, but you can get them out with Git
(next section), using `origin/main` (or your backup branch) as the branch.

## With Git on the command line

For people who use Git. These commands only read; none of them changes or
deletes anything. On Windows, run them in **Git Bash** or **Command Prompt**,
not PowerShell: PowerShell's `>` re-encodes the output and would damage a
binary file such as `.f3d`.

```
# A copy of the repository (or use the add-in's local folder)
git clone https://github.com/you/designs.git
cd designs

# Every backup of one design, newest first
git log --oneline -- designs/Bracket

# Save one file as it was in a given backup (here commit 1a2b3c4)
git show 1a2b3c4:designs/Bracket/Bracket.f3d > Bracket-restored.f3d
```

In the add-in's local folder, use `git log --oneline origin/main -- designs/Bracket`,
because the backups are on `origin/main` there, not on your local branch.
Running `git show` with `>` writes a new file: choose a name that doesn't
overwrite anything.
