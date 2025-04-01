# Autodesk Fusion to GitHub

This Fusion 360 script automatically exports your Autodesk Fusion designs and pushes them directly to a GitHub repository. Perfect for easy version control, automatic backups, and seamless collaboration.

## To Do

1.  **Error Handling:** Improve error handling, especially for Git operations and file operations.
2.  **Git Executable Check:** Add a check to ensure Git is installed and the executable path is correctly set.
3.  **Configuration:** Use a configuration file for storing repository settings.
4.  **Logging:** Implement more comprehensive logging.
5.  **File Versioning:** Implement a better file versioning system.
6.  **Optionally export and push project metadata** Pick which metadata you want to include with the upload
7.  **Export different file formats to GitHub:** Be able to upload STEP, STL, DWG, etc.
8.  **Integrate Fusion Drawing/Electronics/Manufacturing exports** Be able to export drawings, electronics files, and manufacturing data.
9.  **Pull Request Automation:** Add functionality to automate the creation of pull requests.

- ✅ ~~Set more options for uploading to different repositories~~ Done 03/31/25
- ✅ ~~Push to pull request instead of main~~ Done 03/31/25
- ✅ ~~Automatically generate and include commit messages or design notes~~ Done 03/31/25
  

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

Replace the generated `Push_To_GitHub.py` file contents with the script in this repository.


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
