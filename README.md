# Autodesk Fusion to GitHub Add-In

This Fusion 360 Add-In automatically exports your Autodesk Fusion designs and pushes them directly to a GitHub repository. Perfect for easy version control, automatic backups, and seamless collaboration.

## To Do
**Core Functionality & Enhancements**
* [x] **Formalize as Fusion 360 Add-In** `Done 05/07/2025`
    * Package the script as a proper Add-In with a `.manifest` file for persistent UI (button) and easier installation/management by users.
* [ ] **Drawing / Electronics / Manufacturing Export**
    * Enable exporting of related Fusion outputs such as drawings (.dwg, .pdf), schematics/PCB layouts (e.g., .sch, .brd), and CAM toolpaths (e.g., .nc).
* [ ] **Project Metadata Export**
    * Generate and optionally push project metadata (.json or .txt) with each commit (e.g., date, part count, custom notes).
* [ ] **Pull Request Automation**
    * Automatically open a GitHub pull request after pushing a new branch. Requires optional GitHub Personal Access Token (PAT) support with secure handling.
* [ ] **File Versioning Improvements & Changelog**
    * Implement automatic changelog tracking (e.g., appending commit messages to a `CHANGELOG.md`).
    * Explore options for managing versions of exported files beyond standard Git history if needed.
* [ ] **Improved Logging**
    * Store detailed logs (actions, errors, outcomes) locally using Python's `logging` module for more structured file-based logging, or optionally in the repo (e.g., in a dedicated `.logs` directory) for auditing and debugging.
* [ ] **UI/UX Improvements**
    * Convert text-based export format input (currently a `StringValueInput` named `exportFormatsConfig`) to a proper Fusion dropdown/multiselect UI element for easier selection of multiple formats.
    * Further streamline the input flow and command dialogs if needed.
* [ ] **Parameter Export (JSON/CSV)**
    * Export key user parameters (model parameters, user parameters) to a structured file (e.g., JSON, CSV) to be versioned alongside design files.
* [ ] **Bill of Materials (BOM) Export**
    * Integrate BOM generation from the active design and export it as a CSV or JSON file.
* [ ] **Thumbnail/Image Export**
    * Automatically capture a thumbnail image (e.g., PNG) of the current or a predefined view of the model and include it in the commit for visual reference in Git history.
* [ ] **Advanced Export Settings per Format**
    * Provide more granular control over export settings for specific file formats (e.g., STL mesh refinement beyond presets, binary/ASCII options; STEP AP203/AP214 selection).

---
**Completed Milestones**
- ✅ ~~Set more options for uploading to different repositories~~ Done 03/31/25
- ✅ ~~Push to pull request instead of main~~ (Pushes to a new branch, facilitating PRs) Done 03/31/25
- ✅ ~~Automatically generate and include commit messages or design notes~~ (Default template + user input) Done 03/31/25
- ✅ ~~**Error Handling:** Improve error handling, especially for Git operations and file operations.~~ Done 4/1/25
- ✅ ~~**Git Executable Check:** Add a check to ensure Git is installed and the executable path is correctly set.~~ Done 4/1/25
- ✅ ~~**Configuration:** Use a configuration file for storing repository settings.~~ Done 4/1/25
- ✅ ~~**export Format Support** Add export support for step, stl, dwg, dxf~~ Done 4/2/25
- ✅ ~~**Add Comments** Comment the code for understanding~~ Done 4/2/25
- ✅ ~~**Formalize as Fusion 360 Add-In** Package the script as a proper Add-In with a `.manifest` file for persistent UI (button) and easier installation/management by users.~~ Done 5/7/25
---

## Installation and Setup Guide

### ✅ Step 1: Prerequisites

Make sure you have:

1.  **[Git](https://git-scm.com/downloads)** installed on your system and accessible via the command line.
2.  A **GitHub account**.
3.  **Python 3.x** installed on your system (this is mainly for `pip` to install `GitPython`).
4.  The **`GitPython` library**. Install it using pip in your system's Command Prompt or Terminal:
    ```cmd
    pip install GitPython
    ```
    * **Important Note for `GitPython`:** Fusion 360 uses its own embedded Python environment. For this Add-In to find `GitPython`, you might need to:
        * Ensure your system Python's site-packages directory (where `GitPython` gets installed by pip) is accessible or added to the path by Fusion's Python (this can be complex).
        * Alternatively, for more robust distribution, `GitPython` can be "vendored" (included directly) with the Add-In. This Add-In currently assumes `GitPython` can be imported by Fusion's environment. If you encounter `ImportError: No module named 'git'`, this is the likely cause.

### ✅ Step 2: Install the Add-In

1.  **Download or Clone this Add-In:**
    * If you have this Add-In's files (e.g., from a ZIP download or by cloning its own repository if it's hosted on Git), locate the `Push_To_GitHub` folder. This folder should directly contain `Push_To_GitHub.py` and `Push_To_GitHub.manifest`.
2.  **Copy to Fusion 360 Add-Ins Directory:**
    * Copy the entire `Push_To_GitHub` folder into the Fusion 360 Add-Ins directory:
        * **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
            (You can paste this path into your File Explorer address bar)
        * **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
            (In Finder, click "Go" > "Go to Folder..." and paste this path)
3.  **Restart Fusion 360.**

### ✅ Step 3: Configure the Add-In Script (One-Time)

1.  **Git Executable Path (CRITICAL):**
    * Open the `Push_To_GitHub.py` file (located in the `API/AddIns/Push_To_GitHub` folder) with a text editor (like VS Code, Notepad++, etc.).
    * Near the top of the script, find this line:
        ```python
        os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"
        ```
    * **Modify the path** (the part in quotes, e.g., `r"C:\\Program Files\\Git\\cmd\\git.exe"`) to point to the exact location of `git.exe` on your system if it's different. Ensure you use double backslashes `\\` for paths on Windows or a raw string `r"..."`.
2.  **Configure Your Git Identity (if not already done globally):**
    * This tells Git who is making the commits. Open a Command Prompt or Terminal and run:
        ```cmd
        git config --global user.name "Your Name"
        git config --global user.email "you@example.com"
        ```
    Replace "Your Name" and "you@example.com" with your actual Git username and email.

### ✅ Step 4: Using the Add-In

1.  **Find the Button:** After restarting Fusion 360, the "Push to GitHub (ZAC)" button should appear in your Fusion 360 UI. It's typically added to a panel in the "UTILITIES" or "TOOLS" tab of the "DESIGN" workspace.
2.  **Open the Dialog:** Click the "Push to GitHub (ZAC)" button. A dialog box will appear with all options.
3.  **Adding a New Repository for the First Time:**
    * In the "Action / Select Repo" dropdown, choose `+ Add new GitHub repo...`.
    * Fill in the "New Repo Name" field (e.g., `MyFusionProject`). This name is used for the local folder and configuration.
    * Fill in the "Git URL (if adding)" field with the HTTPS or SSH URL of an **empty or existing repository** on GitHub (e.g., `https://github.com/YOUR_USERNAME/YOUR_REPO.git`).
    * Configure the "Export Formats," "Default Commit Template," and "Branch Format" for this new repository.
    * Click "OK." The Add-In will clone the repository (if it's remote and doesn't exist locally in the Add-In's base directory) and save its configuration. You'll need to restart the command (re-click the button) to select this new repo for pushing.
4.  **Pushing to an Existing Configured Repository:**
    * In the "Action / Select Repo" dropdown, choose the name of the repository you want to push to.
    * The fields "Export Formats," "Default Commit Template," and "Branch Format" will be visible. **If you change any of these values, the stored configuration for the selected repository will be updated when you click "OK."**
    * Enter your desired "Commit Message (for this push)." Placeholders like `{filename}` will be replaced with the design's name.
    * Click "OK." The Add-In will:
        1.  Update the selected repository's settings in the configuration file (if you changed them in the dialog).
        2.  Export your active Fusion 360 design using the configured formats.
        3.  Commit the exported files to a new local branch.
        4.  Push the new branch to your GitHub repository.
        5.  A success message will indicate the branch name. You can then create a Pull Request on GitHub to merge the changes if desired.

---

## ✅ Troubleshooting Common Issues

- **Add-In Not Appearing:**
    - Ensure Fusion 360 was restarted after copying the Add-In folder.
    - Double-check the installation path is correct.
    - Validate your `Push_To_GitHub.manifest` file using an online JSON validator. Ensure the `"script"` entry points to `Push_To_GitHub.py`.
- **`ImportError: No module named 'git'` (GitPython Not Found):**
    - This is the most common issue for external libraries. Ensure `pip install GitPython` was successful in your system's Python environment. Fusion's embedded Python needs to be able to find this library. See the "Prerequisites" section for more notes.
- **"Git executable not found" or "Bad Git executable":**
    - Verify the path set for `os.environ['GIT_PYTHON_GIT_EXECUTABLE']` inside the `Push_To_GitHub.py` script is correct and points directly to your `git.exe` (on Windows) or `git` (on macOS/Linux).
    - Ensure Git is installed and its command-line tools are working.
- **Git Push/Pull Errors (e.g., "No upstream branch," authentication failed):**
    - These are often general Git issues. Ensure your local repository is correctly configured to communicate with the remote on GitHub (authentication, correct remote URL). For first-time pushes to a new branch from a local repo, Git sometimes requires `git push -u origin <branchname>`. The script attempts to handle this with `--set-upstream`. If authentication fails, ensure your Git client is configured to authenticate with GitHub (e.g., using a PAT, SSH key).

---

You're now ready to easily manage your Fusion designs via GitHub!

🎉 **Happy designing!** 🎉
