# Fusion to GitHub — Automatic Design Backups

**Back up your Fusion 360 designs to GitHub with one click, keeping a full version history in Git.**

This is a free add-in for Autodesk Fusion 360. Every time you click its button, it saves your design to [GitHub](https://github.com) as a new commit. As long as the repository stays intact, you can go back to any earlier version — if you break a design, lose a file, or just want to see what a part looked like three weeks ago. (Git history is durable but not immutable; see [Known limits](#status-supported-versions-and-known-limits).)

No programming knowledge required. If you can install Fusion 360, you can use this.

---

## What it does

- 💾 **One-click backup** — click a button in Fusion, type a short note, done
- 🕐 **Full version history** — each backup is its own commit; the add-in never overwrites or deletes an earlier one
- 📦 **Multiple file formats** — saves your design as F3D, STEP, STL, IGES, or SAT (you pick)
- 📓 **Automatic logbook** — keeps a `CHANGELOG.md` file listing what changed and when
- 👥 **Easy sharing** — send anyone a link to view or download your designs
- 🔒 **Private if you want** — GitHub lets you keep your designs completely private, for free

### A quick word about the jargon

GitHub was built for programmers, so it uses a few odd words. Here's all you need to know:

| Word | What it actually means |
|------|------------------------|
| **Repository** (or "repo") | A project folder on GitHub that remembers every version of its contents |
| **Commit** | One saved snapshot, with a note about what changed |
| **Branch** | A named snapshot line — each backup this add-in makes gets its own |
| **Push** | Uploading your snapshot to GitHub |

The add-in handles all of this for you. You just click the button.

---

## What you need before installing

1. **Autodesk Fusion 360** on Windows. (macOS is **experimental**: the add-in loads there, but it has not been tested on a Mac.)
2. **A free GitHub account** — sign up at [github.com](https://github.com/signup) (the free plan is all you need, and your designs can be private)
3. **Git** — the free program that talks to GitHub:
   - Download from [git-scm.com/downloads](https://git-scm.com/downloads)
   - Run the installer and **just keep clicking "Next"** — the default options are correct
   - Restart your computer afterwards

That's it. You do not need to learn to use Git — the add-in uses it behind the scenes.

---

## Installing the add-in (5 minutes)

1. **Download the add-in**: open the [latest release](https://github.com/zcohen-nerd/FusionToGitHub/releases/latest) and, under **Assets**, download **`Push_To_GitHub-<version>.zip`** (for example `Push_To_GitHub-0.3.3.zip`).
   Don't use the green **Code → Download ZIP** button: that is the source code, not the add-in.

2. **Open your Fusion add-ins folder:**
   - **Windows**: press `Windows key + R`, paste this, and press Enter:
     `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
   - **Mac**: in Finder press `Cmd + Shift + G`, paste this, and press Enter:
     `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`

3. **Unzip the file into that folder.**
   - **Windows**: right-click the ZIP → **Extract All…**, set the destination to the `AddIns` folder from step 2 (remove the `Push_To_GitHub-<version>` part Windows adds to the end), and click **Extract**.
   - **Mac**: double-click the ZIP, then drag the `Push_To_GitHub` folder it creates into the `AddIns` folder.

   You should end up with exactly this:

   ```
   AddIns/
   └── Push_To_GitHub/
       ├── Push_To_GitHub.manifest
       ├── Push_To_GitHub.py
       └── (4 more files)
   ```

   The folder must be called exactly `Push_To_GitHub`, matching the files inside it, and must sit directly in `AddIns`, not in an extra folder.

4. **Restart Fusion 360.**

5. **Turn the add-in on:** in Fusion, open the **UTILITIES** tab, click **ADD-INS**, find **Push_To_GitHub** in the Add-Ins list, and click **Run**. (Tick "Run on Startup" so it's always available.)

You should now see a **Push to GitHub** button in your toolbar.

> **Button not showing up?** Check the folder layout in step 3, restart Fusion completely, and see the [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

### Upgrading from an earlier version

Versions before 0.3.3 were installed by copying files by hand, often into a folder called `FusionToGitHub`. To switch to the release ZIP:

1. In Fusion, open **UTILITIES → ADD-INS**, select the old add-in, click **Stop**, and untick **Run on Startup**.
2. Quit Fusion.
3. Delete the old add-in folder from the `AddIns` folder. Your saved repositories and settings are kept: they are stored in `.fusion_git_repos.json` in your home folder, not in the add-in folder. A token stored with **Manage Token…** stays in Windows Credential Manager.
4. Install the new version as described above.

Don't keep two copies installed. Both would load, and you could get two buttons or duplicate pushes.

---

## First-time setup (5 minutes)

You only do this once per project.

### Step 1 — Create a home for your designs on GitHub

1. Go to [github.com/new](https://github.com/new) (sign in if asked)
2. Give the repository a name, e.g. `my-fusion-designs`
3. Choose **Private** if you don't want the world to see your designs
4. Click **Create repository**
5. **Copy the page's web address** from your browser's address bar — it looks like
   `https://github.com/yourname/my-fusion-designs`

### Step 2 — Connect Fusion to it

1. In Fusion, click the **Push to GitHub** button
2. The dropdown at the top is already set to **"🆕 Set up new GitHub repository..."** — leave it
3. **Paste the web address** you copied into the **GitHub URL** box
   (the add-in tidies it up automatically — you can leave the Repository Name blank and it will figure it out)
4. Click **Browse…** to pick a folder on your computer for local copies, or accept the suggested one
5. Click **OK**

The add-in sets everything up **and pushes your first backup right away**. From now on, your project appears in the dropdown, ready to use.

> **Two one-time questions may pop up on your first push — both are normal:**
> 1. The add-in may ask for **your name and email**. Git stamps every snapshot with them, like signing your work. Type them once and you're done.
> 2. A window may ask you to **sign in to GitHub**. Follow the prompts once and it remembers you.

---

## Everyday use (30 seconds)

1. Open your design in Fusion
2. Click **Push to GitHub**
3. Type a short note about what you changed — e.g. *"made the bracket holes 5mm"*
4. Click **OK**

A success message tells you exactly what was backed up. That's the whole workflow.

### Where do my files go on GitHub?

Each backup gets its own **snapshot branch** with a name like `fusion-export/Bracket-20260708-143022` (design name + date + time). To see your files on GitHub:

1. Open your repository page
2. Click the **branch dropdown** (it says `main` near the top-left)
3. Pick any snapshot to view or download the files from that moment

Each snapshot is built on top of the latest `main` on GitHub. The add-in never overwrites an earlier snapshot — each is its own commit, and they stay available as long as the repository does. (Teams that want to review and merge snapshots into `main` should read the [Team Guide](docs/TEAM_GUIDE.md).)

The add-in **doesn't change the local folder** you picked during setup: it builds each backup directly from the exported files and sends it to GitHub. So the exports won't appear in that folder, and anything you were doing there (unsaved edits, other branches) is left exactly as it was.

### Size limits

GitHub rejects files of 100 MB or more, and warns about files over 50 MB. The add-in checks before pushing: it refuses an export of 100 MB or more and asks before pushing one over 50 MB. Every version is kept, so a repository grows with each backup. To keep exports small, untick formats you don't need, or lower the STL mesh refinement.

---

## Choosing file formats

In the dialog's **Export Formats** section you can pick any combination:

| Format | Choose it when… |
|--------|-----------------|
| **F3D** | You want the *complete* Fusion file — sketches, timeline, everything (recommended: always keep this on) |
| **STEP** | You share parts with people using other CAD software |
| **STL** | You 3D-print your parts |
| **IGES** | Someone asks for it (older CAD software) |
| **SAT** | Someone asks for it (ACIS-based CAD software) |

The default (F3D + STEP + STL) is a good all-round choice.

---

## If something goes wrong

The add-in explains problems in plain messages and keeps your work safe: it never deletes or overwrites an earlier backup, and it never force-pushes, so it can't overwrite anyone else's work on GitHub either. The three most common hiccups:

| Problem | Fix |
|---------|-----|
| **No button in the toolbar** | Restart Fusion completely; check the files are in the right folder (see Installing above) |
| **"Git executable not found"** | Install Git from [git-scm.com](https://git-scm.com/downloads) with default options, then restart your computer |
| **Sign-in / permission errors** | Make sure you can open your repository's page on github.com while signed in; then try again |

- **See what happened**: expand **Logging** in the dialog and click **Open Log File…**
- **More help**: the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) covers everything else

---

## Security & your GitHub credentials

Short version:

- **By default**, the add-in doesn't touch your credentials at all — it runs
  `git`, and Git's own Credential Manager handles the one-time browser sign-in.
- **Optionally (Windows)**, you can store a Personal Access Token via
  **Manage Token…**; it goes into Windows Credential Manager and is passed to
  Git through a throwaway helper that never writes it to disk.
- Prefer a **fine-grained token** limited to the one repository, with
  **Contents: Read and write** and nothing else.
- **Never** put a token in a repo file, a remote URL, a commit message, a
  screenshot, or a bug report. If one leaks, revoke it on GitHub right away.

Full details — exactly what is stored where, how to delete vs. revoke a token,
and how to report a security problem — are in **[SECURITY.md](SECURITY.md)**.

---

## Status, supported versions, and known limits

- **Version:** **`0.4.0`**. The version is set once, in the add-in manifest;
  the runtime constant, the CLI `--version`, the log banner, the README and the
  top `CHANGELOG.md` entry must match it. CI tests (`T_VERSION`, `T_RELEASE`)
  fail if they drift, and the release workflow refuses a Git tag that doesn't
  match. See [`CHANGELOG.md`](CHANGELOG.md).
- **Operating system:** **Windows** is supported. **macOS is experimental**:
  the add-in is declared for Mac and its automated Git tests run on macOS, but
  nobody has tested it inside Fusion on a Mac yet. If you try it, please report
  what happens in an issue. The optional **stored-token** feature is
  **Windows-only**; on macOS you rely on Git Credential Manager's browser
  sign-in, which is not included with every macOS Git install.
- **Autodesk Fusion:** current Fusion, any recent version — it uses the stable
  design-export API (F3D / STEP / STL / IGES / SAT). DWG/DXF are intentionally
  not offered; Fusion's export API does not produce them.
- **Git:** a recent Git (2.20+) with **Git Credential Manager** enabled — the
  default in modern Git for Windows / macOS installers. `git` must be on `PATH`
  (or at the Windows fallback `C:\Program Files\Git\bin\git.exe`).
- **You create the GitHub repository yourself** on github.com; the add-in never
  creates one via the API.
- **Every push makes a new branch** (`fusion-export/<design>-<timestamp>`),
  built on the latest `main` on GitHub. It only adds to `main` if you name
  `main` in Branch Name Override, and then it asks first. Merging snapshots into
  `main` is a manual step — see the [Team Guide](docs/TEAM_GUIDE.md). If the
  GitHub repository is completely empty, the first backup also adds a small
  first commit to `main` (a `.gitattributes` file that stops Git from altering
  CAD files).
- **Your local folder is never changed.** Backups are built straight from the
  exported files, so uncommitted work, other branches and stashes in the local
  repository are untouched, whether a push succeeds or fails.
- **Nothing can hang forever.** Every Git step has a time limit (10 minutes for
  network steps, which includes a GitHub sign-in window, and 1 minute for local
  ones). If one is reached, the push stops and nothing on GitHub changes.
- **Backups:** this backs up *exported* CAD files to a Git branch. It is a
  complement to, not a replacement for, Fusion's own cloud version history.
  Keep both.
- **History is durable, not immutable.** A successful push creates Git history,
  and this add-in never rewrites or deletes it. But Git history *can* be
  altered: anyone with write access can force-push over a branch, delete a
  branch, or delete the whole repository, and GitHub itself can have outages or
  close an account. Treat this as a strong safety net, not a permanent archive —
  keep an independent backup of anything you cannot afford to lose.
- **History grows:** every export is kept as its own commit, and CAD
  files are binary — a long-lived backup repo can get large (there is no Git
  LFS integration).
- **Automated tests:** 25, run in CI on Ubuntu and Windows across Python
  3.10–3.12, plus macOS (`python tests/test_runner.py`). The Fusion UI itself is verified
  by the manual checklist in [`tests/MANUAL_TESTS.md`](tests/MANUAL_TESTS.md).

### First success, end to end

1. Create an (empty) repo on [github.com/new](https://github.com/new) — Private
   is fine — and copy its URL.
2. Install the add-in (above) and click **Push to GitHub** in Fusion.
3. Leave the dropdown on **"Set up new GitHub repository…"**, paste the URL,
   pick a local folder, click **OK**.
4. Answer the two one-time prompts if they appear (your Git name/email, then a
   GitHub sign-in window).
5. The first backup pushes automatically. After that: open a design → click the
   button → type a note → **OK**.

---

## More documentation

| Guide | What's in it |
|-------|--------------|
| [Getting Started](docs/GETTING_STARTED.md) | The full first-time walkthrough with more detail |
| [User Guide](docs/USER_GUIDE.md) | Every feature explained — formats, templates, subfolders, tokens |
| [Quick Reference](docs/QUICK_REFERENCE.md) | One-page cheat sheet |
| [Installation Guide](docs/INSTALLATION.md) | Detailed install instructions for both platforms |
| [Team Guide](docs/TEAM_GUIDE.md) | Working with multiple people on shared designs |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Fixes for every known problem |

---

## For advanced users

<details>
<summary><b>Extra features in the dialog (click to expand)</b></summary>

- **Commit / branch templates** — customize how snapshot names and notes are generated using `{filename}` and `{timestamp}` placeholders
- **Export Subfolder** — keep exports organized in a folder inside the repository (e.g. `exports/`)
- **Branch Name Override** — push to a specific branch name of your choosing; if the branch already exists, the add-in asks and then adds the new version to it. If GitHub has newer commits on that branch than your computer, the push is refused and nothing on GitHub changes
- **Use Stored Token** (Windows only) — store a GitHub Personal Access Token in Windows Credential Manager so you're never asked to sign in; set it up via **Manage Token…** in the Advanced section. Prefer a **fine-grained** token scoped to just this repo with **Contents: Read and write** — see [SECURITY.md](SECURITY.md).
- **Log Level** — turn on DEBUG logging when investigating a problem

</details>

<details>
<summary><b>For developers (click to expand)</b></summary>

**Project layout**: the add-in lives in [`src/`](src) (`Push_To_GitHub.py` is the Fusion UI; `fusion_git_core.py` and `dialog_helpers.py` are Fusion-free modules), docs in [`docs/`](docs), tests in [`tests/`](tests).

**Testing** — 25 automated tests, including end-to-end git pipeline tests against local repositories:

```
python tests/test_runner.py
```

**CLI harness** — run the whole git pipeline without Fusion (useful for CI):

```
python src/push_cli.py --repo C:\path\to\repo --files exports/model.step --design-name BracketV4
```

**How a push works**: ask GitHub for its branches (`ls-remote`) → fetch the tip to build on → build a commit in a temporary index (`read-tree`, `hash-object --no-filters`, `update-index`, `write-tree`, `commit-tree`) whose parent is that tip → plain push, rebuilding on the new tip if GitHub moved meanwhile (up to 3 attempts). The user's working tree, index, stash, HEAD and local branches are never touched, and nothing is force-pushed. Commit hooks don't run for these commits; a `pre-push` hook does. `push_cli.py --mode single` adds exports to one branch instead of creating snapshot branches.

**Contributing**: bug reports and pull requests welcome — please include your OS, Fusion version, and the log file (`~/.PushToGitHub_AddIn_Data/PushToGitHub.log`) with any bug report, and add tests for new functionality.

</details>

---

## License

Free and open source under the [MIT License](LICENSE).

## Building and releasing

Developers: `python scripts/package.py build` builds and checks the add-in ZIP
from the current commit. Releases are made by pushing a version tag; CI builds
the ZIP and creates a draft release for review. See
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).
