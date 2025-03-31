# Autodesk Fusion to GitHub

This Fusion 360 script automatically exports your Autodesk Fusion designs and pushes them directly to a GitHub repository. Perfect for easy version control, automatic backups, and seamless collaboration.

## To Do

- Set more options for uploading to different repositories
- Integrate Fusion Drawing/Electronics/manufacturing exports
- Export different file formats to GitHub
- Create a user-friendly config file to simplify setup
- Integrate with GitHub Actions for automated downstream processing or notifications
- Optionally export and push project metadata
- ✅ ~~Push to pull request instead of main~~ Done 03/31/25
- ~~Automatically generate and include commit messages or design notes~~ Done 03/31/25
  

# Autodesk Fusion to GitHub Integration Guide

This guide will show you how to set up Autodesk Fusion to automatically export `.f3d` design files and push them directly to GitHub.

---

## ✅ Step 1: Prerequisites

Make sure you have:

- **[Git for Windows](https://git-scm.com/downloads)** installed
- **Python 3.x** installed ([Download here](https://www.python.org/downloads/))
- A **GitHub account** with a repository created

---

## ✅ Step 2: Clone GitHub Repository

- Open Command Prompt and clone your GitHub repository locally:

```cmd
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

Replace `YOUR_USERNAME` and `YOUR_REPO` appropriately.

---

## ✅ Step 3: Install GitPython

In Command Prompt:

```cmd
pip install GitPython
```

---

## ✅ Step 4: Create Fusion 360 Script

- Open Autodesk Fusion
- Click **Utilities → Scripts and Add-ins**
- Click **Create**
  - Name: `Push_To_GitHub`
  - Language: **Python**
- Click **Create**

---

## ✅ Step 5: Configure the Script

Replace the generated `Push_To_GitHub.py` file contents with:

```python
import adsk.core, adsk.fusion, traceback
import os, shutil, re
from git import Repo
from datetime import datetime

# Set Git executable path (edit if needed)
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\Program Files\Git\cmd\git.exe"

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox('No active Fusion design', 'Error')
            return

        # Prompt for commit message
        commit_input = ui.inputBox("Enter a commit message for GitHub:", "Commit Message", "Updated design")[0]
        if not commit_input or not commit_input.strip():
            ui.messageBox("Commit message cannot be empty.")
            return

        # Paths (customize these)
        git_repo_path = os.path.expanduser(r"C:\path\to\your\local\repo")
        temp_dir = os.path.expanduser(r"C:\temp\FusionExport")

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Clean version number from filename (e.g., remove " v42")
        raw_name = design.rootComponent.name
        clean_name = re.sub(r' v\d+$', '', raw_name)
        filename = f"{clean_name}.f3d"
        export_path = os.path.join(temp_dir, filename)

        # Export Fusion file
        export_mgr = design.exportManager
        options = export_mgr.createFusionArchiveExportOptions(export_path)
        export_mgr.execute(options)

        if not os.path.exists(export_path):
            ui.messageBox('Export failed.')
            return

        # Copy to Git repo
        shutil.copy2(export_path, git_repo_path)

        # Git operations
        repo = Repo(git_repo_path)

        # Check for unfinished rebase
        rebase_path = os.path.join(git_repo_path, '.git', 'rebase-merge')
        if os.path.exists(rebase_path):
            ui.messageBox("Git is stuck in an unfinished rebase. Please resolve it manually:\n\n"
                          " - git rebase --abort\n"
                          " - OR git rebase --continue\n"
                          " - OR delete .git/rebase-merge if safe")
            return

        if repo.head.is_detached:
            ui.messageBox('Git repo is in a detached HEAD state. Please check out a branch manually before running this script.')
            return

        # Create a new branch for this push
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M')
        branch_name = f"fusion-auto-{timestamp}"
        repo.git.checkout('-b', branch_name)

        repo.git.add(filename)
        repo.index.commit(commit_input.strip())

        try:
            repo.git.push('--set-upstream', 'origin', branch_name)
        except Exception as push_error:
            ui.messageBox(f'Git push failed:\n{str(push_error)}')
            return

        ui.messageBox(f'Successfully pushed to branch \"{branch_name}\".\n\n"
                      "Please open a Pull Request on GitHub to merge your changes into main.")
        shutil.rmtree(temp_dir)

    except Exception as e:
        ui.messageBox(f'Script error:\n{traceback.format_exc()}')

    adsk.autoTerminate(True)
```

**✅ Customize the git_repo_path and temp_dir for your machine.**

**Configure your Git Identity Once**

git config --global user.name "Your Name"

git config --global user.email "you@example.com"

---

## ✅ Step 6: Initialize Local Git Repository (first-time only)

In Command Prompt:

```cmd
cd C:\path\to\your\local\repo
git init
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git pull origin main
git push -u origin main
```

---

## ✅ Step 7: Add Script Button to Fusion Toolbar

- In Fusion → **Utilities → Scripts and Add-ins**
- Select your script and click **Add to toolbar**

---

## ✅ Step 8: Using the Workflow

1. Design in Fusion
2. Click your new **Push to GitHub** button
3. Your design is now versioned and pushed to GitHub!

---

## ✅ Troubleshooting Common Issues

- **GitPython Not Found:** Ensure `pip install GitPython` was successful.
- **"Bad Git executable":** Ensure Git executable path (`git.exe`) is correct.
- **"No upstream branch":** Run `git push -u origin main` once manually.

---

You're now ready to easily manage your Fusion designs via GitHub!

🎉 **Happy designing!** 🎉
