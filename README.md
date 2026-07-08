# Fusion to GitHub — Automatic Design Backups

**Back up your Fusion 360 designs to the cloud with one click — with a complete history of every version you ever saved.**

This is a free add-in for Autodesk Fusion 360. Every time you click its button, it saves your design to [GitHub](https://github.com) — a free online storage service that keeps *every* version of your files forever. If you ever break a design, lose a file, or just want to see what a part looked like three weeks ago, you can always get it back.

No programming knowledge required. If you can install Fusion 360, you can use this.

---

## What it does

- 💾 **One-click backup** — click a button in Fusion, type a short note, done
- 🕐 **Full version history** — every backup is kept forever; nothing is ever overwritten
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

1. **Autodesk Fusion 360** (Windows or Mac)
2. **A free GitHub account** — sign up at [github.com](https://github.com/signup) (the free plan is all you need, and your designs can be private)
3. **Git** — the free program that talks to GitHub:
   - Download from [git-scm.com/downloads](https://git-scm.com/downloads)
   - Run the installer and **just keep clicking "Next"** — the default options are correct
   - Restart your computer afterwards

That's it. You do not need to learn to use Git — the add-in uses it behind the scenes.

---

## Installing the add-in (5 minutes)

1. **Download this project**: click the green **Code** button at the top of this page, then **Download ZIP**, and unzip it anywhere.

2. **Find your Fusion add-ins folder:**
   - **Windows**: press `Windows key + R`, paste this, and press Enter:
     `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
   - **Mac**: in Finder press `Cmd + Shift + G`, paste this, and press Enter:
     `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`

3. **Create a new folder** there called `FusionToGitHub`, and **copy everything from the ZIP's `src` folder into it** — all the files, not just some of them.

4. **Restart Fusion 360.**

5. **Turn the add-in on:** in Fusion, open the **UTILITIES** tab, click **ADD-INS**, find **"Push to GitHub (ZAC)"** in the Add-Ins list, and click **Run**. (Tick "Run on Startup" so it's always available.)

You should now see a **Push to GitHub** button in your toolbar.

> **Button not showing up?** Restart Fusion completely and check the [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

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

> The first time you push, a window may pop up asking you to **sign in to GitHub** — that's normal. Follow the prompts once and it remembers you.

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

Nothing is ever overwritten — every backup stays available forever. (Teams that want to review and merge snapshots into `main` should read the [Team Guide](docs/TEAM_GUIDE.md).)

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

The add-in explains problems in plain messages, keeps your work safe, and never deletes anything. The three most common hiccups:

| Problem | Fix |
|---------|-----|
| **No button in the toolbar** | Restart Fusion completely; check the files are in the right folder (see Installing above) |
| **"Git executable not found"** | Install Git from [git-scm.com](https://git-scm.com/downloads) with default options, then restart your computer |
| **Sign-in / permission errors** | Make sure you can open your repository's page on github.com while signed in; then try again |

- **See what happened**: expand **Logging** in the dialog and click **Open Log File…**
- **More help**: the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) covers everything else

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
- **Branch Name Override** — push to a specific branch name of your choosing; if the branch already exists, the add-in asks and then adds the new version to it
- **Force Push (skip pull)** — for when your local copy and GitHub disagree and you want your version to win
- **Use Stored Token** (Windows) — store a GitHub Personal Access Token in Windows Credential Manager so you're never asked to sign in; set it up via **Manage Token…** in the Advanced section
- **Log Level** — turn on DEBUG logging when investigating a problem

</details>

<details>
<summary><b>For developers (click to expand)</b></summary>

**Project layout**: the add-in lives in [`src/`](src) (`Push_To_GitHub.py` is the Fusion UI; `fusion_git_core.py` and `dialog_helpers.py` are Fusion-free modules), docs in [`docs/`](docs), tests in [`tests/`](tests).

**Testing** — 16 automated tests, including end-to-end git pipeline tests against local repositories:

```
python tests/test_runner.py
```

**CLI harness** — run the whole git pipeline without Fusion (useful for CI):

```
python src/push_cli.py --repo C:\path\to\repo --files exports/model.step --design-name BracketV4
```

**How a push works**: stash local changes → pull latest → create snapshot branch → copy exports in → update changelog → commit → push → restore your original branch and changes. Conflicts abort cleanly; cancellations restore everything.

**Contributing**: bug reports and pull requests welcome — please include your OS, Fusion version, and the log file (`~/.PushToGitHub_AddIn_Data/PushToGitHub.log`) with any bug report, and add tests for new functionality.

</details>

---

## License

Free and open source under the [MIT License](LICENSE).
