# Installing, updating and removing Push to GitHub

This is the one place for installing the add-in, updating it, going back to an
earlier version, and removing it. For using it, see the [user guide](USER_GUIDE.md).

- [What you need](#what-you-need)
- [Install from the release ZIP](#install-from-the-release-zip)
- [Install with the Community Store](#install-with-the-community-store)
- [macOS (experimental)](#macos-experimental)
- [Check that it works](#check-that-it-works)
- [Update to a new version](#update-to-a-new-version)
- [Go back to an earlier version](#go-back-to-an-earlier-version)
- [Upgrading from a version before 0.3.3](#upgrading-from-a-version-before-033)
- [Uninstall](#uninstall)

---

## What you need

| | |
|---|---|
| **Autodesk Fusion** | A current version. The add-in uses Fusion's standard export API. |
| **Operating system** | Windows 10 or 11. macOS is [experimental](#macos-experimental). |
| **Git** | 2.30 or newer recommended, from [git-scm.com/downloads](https://git-scm.com/downloads). On Windows, install it with the default options: they include **Git Credential Manager**, which opens a GitHub sign-in window when needed. |
| **A GitHub account** | The free plan is enough. Create the repository for your designs on github.com yourself; [Private](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) is best for designs you don't want to publish. |
| **Internet access** | To github.com, while a backup or Check My Setup runs. |

Git must be installed before the add-in can back anything up. If it's missing,
the add-in says so when you first open it, with a download link.

## Install from the release ZIP

1. Open the [latest release](https://github.com/zcohen-nerd/FusionToGitHub/releases/latest)
   and, under **Assets**, download **`Push_To_GitHub-<version>.zip`**. It has a
   matching `.sha256` file if you want to check the download.
   Don't use the green **Code → Download ZIP** button or a clone of the
   repository: that is the source code, arranged differently from what Fusion
   expects.
2. Open Fusion's add-ins folder:
   - **Windows:** press **Windows key + R**, paste
     `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns` and press Enter.
   - **macOS:** in Finder press **Cmd + Shift + G**, paste
     `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
     and press Enter.

   If that folder doesn't exist, use `…\Autodesk\Autodesk Fusion\API\AddIns`
   (`…/Autodesk/Autodesk Fusion/API/AddIns` on macOS), whichever exists.
3. Unzip into that folder:
   - **Windows:** right-click the ZIP → **Extract All…**. Set the destination to
     the `AddIns` folder, and delete the `\Push_To_GitHub-<version>` that Windows
     adds to the end of the path. Click **Extract**.
   - **macOS:** double-click the ZIP and drag the `Push_To_GitHub` folder it
     creates into the `AddIns` folder.

   You should have exactly this:

   ```
   AddIns/
   └── Push_To_GitHub/
       ├── Push_To_GitHub.manifest
       ├── Push_To_GitHub.py
       ├── resources/          (the button's icons)
       └── … more .py files, AddInIcon.svg and LICENSE
   ```

   The folder must be named exactly `Push_To_GitHub`, like the `.manifest` and
   `.py` files inside it, and sit directly in `AddIns`. An extra folder level
   (`AddIns/Push_To_GitHub-0.8.0/Push_To_GitHub/…`) stops Fusion from finding it.
4. In Fusion, open **UTILITIES → ADD-INS**, select
   **Push to GitHub** on the **Add-Ins** tab, click **Run**, and tick **Run on
   Startup**.

## Install with the Community Store

The [Fusion Community Store](https://github.com/4FusionLab/CommunityStore) is a
free, community-made add-in that installs and updates add-ins from their GitHub
releases. With it installed, find **Push to GitHub** in it and install it there;
it downloads the same release ZIP and updates it when a new version is
published. The Store only offers published releases.

Don't install the same add-in both ways: see [two copies](#two-copies-installed).

## macOS (experimental)

The add-in is declared for macOS and its automated tests run on macOS, but it
hasn't been tested inside Fusion on a Mac. If you try it, please report what
happens in an [issue](https://github.com/zcohen-nerd/FusionToGitHub/issues).

- **Git:** install it with [Homebrew](https://brew.sh) (`brew install git`) or
  Apple's Command Line Tools (`xcode-select --install`). The add-in looks for
  Git in `/opt/homebrew/bin`, `/usr/local/bin` and `/usr/bin`, because Fusion
  started from the Dock doesn't see your terminal's settings.
- **Signing in to GitHub:** install
  [Git Credential Manager](https://github.com/git-ecosystem/git-credential-manager#readme).
  macOS's built-in keychain helper can reuse a saved sign-in but can't ask for
  a new one from inside Fusion. **Check My Setup** tells you which one you have.
- **Stored tokens** (Advanced → Use stored token) are Windows-only.

## Check that it works

1. The **Push to GitHub** button (a blue cube with an orange branch) is in the
   **ADD-INS** panel of the Design workspace. The add-in also appears in
   **UTILITIES → ADD-INS** with the same icon.
2. Click it, then **Check My Setup…**. With no saved repository yet, it checks
   Git and your sign-in helper; once you have backed up, it also tests the
   connection to your repository.

If the button doesn't appear, see
[Troubleshooting → The add-in doesn't appear](TROUBLESHOOTING.md#the-add-in-doesnt-appear-or-has-no-button).

## Update to a new version

> **Note:** versions 0.6.0 and later are in development and not yet published;
> the current release is 0.4.0. What this guide says about them describes how
> they are designed to behave, and is checked in Fusion before they are
> released.

Your settings, saved repositories and stored token are kept: they aren't in
the add-in's folder.

**With the Community Store:** update it there. From 0.6.0 on, the new version
is designed to start without restarting Fusion (not yet confirmed in Fusion
itself; restart Fusion if it doesn't).

**With a release ZIP:**
1. In **UTILITIES → ADD-INS**, select **Push to GitHub** and click **Stop**.
2. Delete everything inside the `AddIns/Push_To_GitHub` folder, and unzip the
   new version's `Push_To_GitHub` folder in its place (as in
   [Install](#install-from-the-release-zip), step 3).
3. Click **Run**. The log file (Help & Privacy → Open Log File…) contains a
   line ending in "Add-In Loaded and running. <version>" that says which
   version started.

From 0.6.0 on, this is designed to work without restarting Fusion (not yet
confirmed in Fusion itself). When updating *from* a
version before 0.6.0, restart Fusion after step 2: those versions can leave
their old modules loaded. If anything looks wrong after an update, restarting
Fusion is always safe.

## Go back to an earlier version

Use the same steps as an update, with the earlier version's ZIP from the
[releases page](https://github.com/zcohen-nerd/FusionToGitHub/releases).

**Settings when going back.** From 0.6.0 on, the settings file
(`.fusion_git_repos.json` in your home folder) has a new layout:

- **Going back to 0.6.0 or later:** nothing to do. A newer layout than the add-in
  knows is shown read-only, so an older version can't damage it.
- **Going back to 0.4.0 or earlier:** those versions don't understand the new
  layout. Before running them, rename `.fusion_git_repos.json` to keep it, and
  copy `.fusion_git_repos.json.v0-backup`, the copy the newer version made of
  your original settings, to `.fusion_git_repos.json`. Repositories you added
  after updating aren't in that copy; add them again. Coming forward again,
  put your kept file back.

Backups already on GitHub stay exactly as they are whichever version you run.

## Upgrading from a version before 0.3.3

Before 0.3.3 the add-in was installed by copying files by hand, often into a
folder called `FusionToGitHub`. To switch to the release ZIP:

1. In **UTILITIES → ADD-INS**, select the old add-in, click **Stop**, and untick
   **Run on Startup**.
2. Quit Fusion, and delete the old add-in folder from `AddIns`.
3. Install the release ZIP as above.

Your saved repositories and settings are kept.

## Two copies installed

Keep one copy only. Since 0.6.0 a second copy (for example one installed by
hand and one by the Community Store, or an old folder left behind) shows a
warning naming both folders and adds no second button. Remove one in
**UTILITIES → ADD-INS** (select it, **Stop**, untick **Run on Startup**), delete
its folder, and restart Fusion.

## Uninstall

1. In **UTILITIES → ADD-INS**, select **Push to GitHub**, click **Stop** and
   untick **Run on Startup**.
2. Delete the `AddIns/Push_To_GitHub` folder (or uninstall it in the Community
   Store).

That removes the add-in. These stay on your computer until you delete them,
because they hold your data:

| What | Where | To remove |
|---|---|---|
| Saved repositories and settings | `.fusion_git_repos.json` in your home folder (plus `.v0-backup`, `.corrupt-…` copies if any) | Delete the files |
| Log files | `.PushToGitHub_AddIn_Data/` in your home folder | Delete the folder, or **Help & Privacy → Clear Log** before uninstalling |
| Stored tokens (Windows) | Windows Credential Manager → **Windows Credentials**, entries `FusionToGitHub::<repository name>` | Remove them there, or **Manage Token… → Delete** before uninstalling; also revoke the token on GitHub (Settings → Developer settings) |
| Leftover credential folders (Windows) | `%LOCALAPPDATA%\PushToGitHub` (normally empty) | Delete the folder |
| Local copies of your repositories | `FusionGitRepos/` in your home folder, or the folders you chose | Delete them if you don't need them; **your backups stay on GitHub** |
| Your Git name and email, if you chose "all repositories" | Your global Git settings (`git config --global --list`) | Change them with `git config --global user.name …`, or leave them |

Nothing is removed from GitHub. To delete backups there, delete the repository
on github.com (Settings → Danger Zone): that cannot be undone.
