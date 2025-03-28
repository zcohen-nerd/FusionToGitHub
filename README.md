# Fusion 360 to GitHub Integration Guide

This guide will show you how to set up Autodesk Fusion 360 to automatically export `.f3d` design files and push them directly to GitHub.

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

- Open Fusion 360
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
import os, shutil
from git import Repo

# Set Git executable path (modify if needed)
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\Program Files\Git\cmd\git.exe"

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox('No active Fusion design', 'Error')
            return

        # Set paths
        git_repo_path = os.path.expanduser(r"C:\path\to\your\local\repo")
        temp_dir = os.path.expanduser(r"C:\temp\FusionExport")

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Export Fusion file
        filename = f"{design.rootComponent.name}.f3d"
        export_path = os.path.join(temp_dir, filename)

        export_mgr = design.exportManager
        options = export_mgr.createFusionArchiveExportOptions(export_path)
        export_mgr.execute(options)

        # Copy and commit to Git
        shutil.copy2(export_path, git_repo_path)

        repo = Repo(git_repo_path)
        repo.git.add(filename)
        repo.index.commit(f"Updated {filename}")
        repo.remote(name='origin').push()

        ui.messageBox(f'Successfully pushed "{filename}" to GitHub.')

        shutil.rmtree(temp_dir)

    except Exception as e:
        ui.messageBox(f'Error:\n{traceback.format_exc()}')
```

**Edit paths (`git_repo_path`, `temp_dir`) to match your setup.**

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

- In Fusion 360 → **Utilities → Scripts and Add-ins**
- Select your script and click **Add to toolbar**

---

## ✅ Step 8: Using the Workflow

1. Design in Fusion 360
2. Click your new **Push to GitHub** button
3. Your design is now versioned and pushed to GitHub!

---

## ✅ Troubleshooting Common Issues

- **GitPython Not Found:** Ensure `pip install GitPython` was successful.
- **"Bad Git executable":** Ensure Git executable path (`git.exe`) is correct.
- **"No upstream branch":** Run `git push -u origin main` once manually.

---

You're now ready to easily manage your Fusion 360 designs via GitHub!

🎉 **Happy designing!** 🎉
