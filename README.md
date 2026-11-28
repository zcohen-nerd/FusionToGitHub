# Fusion to GitHub

**Back up your Autodesk® Fusion designs to a GitHub repository you own, one click at a time, with a dated, annotated history of every version.**

This free add-in for Autodesk Fusion adds a **Push to GitHub** button. Each time you click it, it exports the open design (as a Fusion file, STEP, STL, IGES or SAT: you choose) and adds it, with a note about what changed, to a repository on [GitHub](https://github.com). You can get any earlier version back from GitHub later.

No programming or Git knowledge is needed.

**Status:** version **`0.9.0`** (the 1.0 release candidate) is in development and not yet released. The current release is
[0.4.0](https://github.com/zcohen-nerd/FusionToGitHub/releases/latest). Windows is supported; macOS is experimental (see [Platform support](#platform-support)).

---

## What it does, and what it doesn't

**It does:**
- Export the open design and send it to your GitHub repository when you click the button, with your note.
- Keep each design in its own folder (`designs/<design name>/`) with a `HISTORY.md` that lists every backup: when, your note, and which Fusion version of the design it was.
- Keep every earlier version available on GitHub. The add-in never deletes or overwrites a backup, and never "force-pushes" (replaces what is on GitHub).
- Check that every export worked before anything is sent: if one fails, nothing is sent.

**It doesn't:**
- Back up on its own. You click the button when you want a backup.
- Replace Fusion's own version history. It's an independent copy, outside Autodesk's cloud, in formats other programs can open. Keep both.
- Merge, compare or lock designs between people. See [Teams](docs/TEAMS.md) for what works when several people share a repository.
- Create the GitHub repository for you, or change files in the local folder it uses.

---

## Before you start

1. **Autodesk Fusion** on **Windows**. macOS is experimental.
2. **A GitHub account.** The free plan is enough, and your designs can stay private: [github.com/signup](https://github.com/signup).
3. **Git**, the free program the add-in uses to talk to GitHub: download it from [git-scm.com/downloads](https://git-scm.com/downloads) and install it with the default options. On Windows, those include Git Credential Manager, which handles signing in to GitHub. On a Mac, see [Install → macOS](docs/INSTALL.md#macos-experimental).

> ⚠️ **Use a private repository for designs you don't want to publish.** In a public repository, anyone can see and download every version you back up, including the full Fusion file, and copies can remain in other people's forks even after you delete them. The add-in reminds you before the first backup to each repository.

---

## Install (5 minutes)

1. Open the [latest release](https://github.com/zcohen-nerd/FusionToGitHub/releases/latest) and, under **Assets**, download **`Push_To_GitHub-<version>.zip`**. (Not the green **Code → Download ZIP** button: that is the source code.)
2. Unzip it into Fusion's `AddIns` folder, so that you have `AddIns/Push_To_GitHub/Push_To_GitHub.manifest`. The [installation guide](docs/INSTALL.md#install-from-the-release-zip) shows where that folder is and how to unzip without an extra folder level.
3. In Fusion, turn it on and tick **Run on Startup** ([installation guide, step 4](docs/INSTALL.md#install-from-the-release-zip)).

The **Push to GitHub** button (a blue cube with an orange branch) appears in the **ADD-INS** panel. If you use the [Fusion Community Store](https://github.com/4FusionLab/CommunityStore), you can install and update it from there instead.

Updating, going back to an earlier version and uninstalling are in the **[installation guide](docs/INSTALL.md)**.

---

## Your first backup (5 minutes)

1. On GitHub, [create a new repository](https://github.com/new) (choose **Private**), and copy its address from the browser, for example `https://github.com/you/my-designs`.
2. In Fusion, open the design and click **Push to GitHub**.
3. The Repository list shows **Set up a new GitHub repository…**. Paste the address into **GitHub address**. Leave the suggested local folder as it is.
   *Not sure everything is installed? Click **Check My Setup…** first: it checks Git, your GitHub sign-in and the repository, and says what to fix.*
4. Type a short note in **What changed?**, for example *first version*.
5. Click **Back up now**. (It stays greyed out until everything it needs is filled in; the line under the files says what's missing.)

The first time, the add-in may ask for your name and email (Git labels every backup with them; a [GitHub "noreply" address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email-address) works), and a GitHub sign-in window may open in your browser. Both happen once.

When the backup is done, the add-in says where it went and offers to **open it on GitHub** or **copy the link**.

## Everyday use (30 seconds)

1. Click **Push to GitHub**.
2. Type what changed, for example *holes widened to 5 mm*.
3. Click **Back up now**.

Fusion stays usable while the backup is sent, and **Cancel** in the progress window stops it. The message at the end says truthfully whether anything reached GitHub.

---

## Getting an old version back

Every backup is kept. On GitHub, open the repository, then `designs/<your design>/`:
- `HISTORY.md` lists every backup with its date, note and Fusion version.
- Click a file, then **History**, to see all its versions. Open one and choose **Download raw file**.
- Open the downloaded `.f3d` in Fusion.

The **[backup and restore guide](docs/RESTORE.md)** walks through each step, including STEP and STL files, backups made with older versions, and designs with linked components.

---

## Good to know

- **Where backups go.** New repositories keep one running history on the repository's main branch, in `designs/<design name>/`. The dialog's **Saves to** line shows the branch and folder before you click. **Advanced** lets you keep backups on a branch of their own, or use a separate branch per backup (as versions before 0.7.0 did; repositories set up with those versions keep doing that).
- **Your files in the local folder are never changed.** The add-in builds each backup straight from the exported files, so the local folder doesn't show them, and your files and branches there are left alone (only Git's own records of what is on GitHub are updated).
- **Size limits.** GitHub refuses files of 100 MB or more, so the add-in refuses them too, and asks before sending one over 50 MB. Every version is kept, so the repository grows with each backup. Untick formats you don't need, or lower the STL mesh refinement.
- **Linked components: known limitation.** A backup of a design that contains components linked from other designs **may not restore on its own**; restoring one hasn't been verified yet. The add-in asks before backing up such a design. See [restore → linked components](docs/RESTORE.md#designs-with-linked-components).
- **History is durable, not permanent.** The add-in never rewrites or deletes history, but anyone with write access to the repository can, and GitHub can have outages or close an account. Keep an independent copy of anything you can't afford to lose.
- **Other Git servers.** The add-in is made and tested for GitHub. Other servers that speak Git over https may work, but aren't tested. Links in the summary then go to the repository's main page.

### Platform support

| | Status |
|---|---|
| Windows 10/11 | Supported |
| macOS | **Experimental**: automated tests run on macOS, but the add-in hasn't been tested inside Fusion on a Mac. Sign-in needs Git Credential Manager; stored tokens are Windows-only. Reports are welcome. |
| Git | 2.30 or newer recommended; **Check My Setup** shows your version |
| Fusion | Uses Fusion's standard export API. The Fusion versions tested will be listed here once the release has been checked in Fusion |

---

## Help

- **Check My Setup…** in the dialog finds most problems and says what to do.
- The **[troubleshooting guide](docs/TROUBLESHOOTING.md)** lists every message the add-in shows, with the fix.
- The log file: **Help & Privacy → Open Log File…** in the dialog.
- Questions and bug reports: see **[SUPPORT.md](SUPPORT.md)**. Security problems: **[SECURITY.md](SECURITY.md)** (please don't open a public issue).

## Documentation

| Document | For |
|---|---|
| [Installation guide](docs/INSTALL.md) | Installing, updating, going back to an earlier version, uninstalling |
| [User guide](docs/USER_GUIDE.md) | Every option in the dialog, explained |
| [Backup and restore guide](docs/RESTORE.md) | What a backup contains, and getting a version back |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Messages and problems, with fixes |
| [Teams](docs/TEAMS.md) | Several people and one repository |
| [Privacy](PRIVACY.md) · [Security](SECURITY.md) | What is stored and sent; stored tokens |
| [Changelog](CHANGELOG.md) | What changed in each version |
| [Contributing](CONTRIBUTING.md) | Developing, testing and releasing |

## Credits and licence

Created by Zac Cohen. Contributors are credited in the [changelog](CHANGELOG.md); thanks to [DiegoV71](https://github.com/DiegoV71) for reporting the missing installable release and the same-session update problem (#11), the stable add-in ID and release ZIP layout (#12), and the 0.3.3 packaging alignment (#14). Released under the [MIT licence](LICENSE).

---

*Autodesk and Fusion are registered trademarks or trademarks of Autodesk, Inc., and/or its subsidiaries and/or affiliates in the USA and/or other countries. GitHub is a trademark of GitHub, Inc. This add-in is an independent project; it is not affiliated with, endorsed by or sponsored by Autodesk or GitHub.*
