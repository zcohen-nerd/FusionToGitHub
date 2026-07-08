# Getting Started with FusionToGitHub V7.7

## Welcome! 👋

FusionToGitHub is an add-in for Autodesk Fusion 360 that automatically backs up your designs to GitHub. Think of it as "Save to Cloud" but with powerful version control, collaboration features, and a complete history of your design changes.

**What this add-in does:**
- Exports your Fusion 360 designs in multiple formats (F3D, STEP, STL, etc.)
- Automatically commits them to a GitHub repository
- Creates a changelog of your design evolution
- Manages branches and version history
- Enables easy sharing and collaboration

**Who should use this:**
- Fusion 360 users who want automatic backups
- Engineers sharing designs with team members
- Makers who want to version control their projects
- Anyone who wants professional design management

---

## 🚀 Quick Start (15 minutes)

### Step 1: Prerequisites Check ✅

Before installing, make sure you have:

1. **Autodesk Fusion 360** installed and working
2. **Git** installed on your computer
   - Download from: https://git-scm.com/downloads
   - During installation, choose "Git from the command line and also from 3rd-party software"
3. **GitHub account** (free at github.com)
4. **GitHub authentication ready** *(optional — on Windows the first push
   normally opens a browser sign-in, and that's all you need)*
   - Only if you prefer a stored token: GitHub → Settings → Developer
     settings → Personal access tokens → Tokens (classic) → "Generate new
     token (classic)" with the `repo` scope, and save it securely

### Step 2: Install the Add-in 📦

1. **Download** the FusionToGitHub files
2. **Locate your Fusion 360 add-ins folder:**
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. **Create a new folder** called `FusionToGitHub`
4. **Copy everything from the download's `src` folder** into it:
   - `Push_To_GitHub.py`
   - `Push_To_GitHub.manifest`
   - `AddInIcon.svg`
   - `fusion_git_core.py` (required)
   - `dialog_helpers.py` (required)
   - `push_cli.py`
   - `diagnostic.py`

   ⚠️ The add-in will not load if `fusion_git_core.py` or
   `dialog_helpers.py` are missing — copy the whole `src` folder contents.
5. **Restart Fusion 360** completely

### Step 3: Enable the Add-in 🔧

1. In Fusion 360, go to **UTILITIES** tab
2. Click **ADD-INS** button
3. Find "Push to GitHub (ZAC)" in the list
4. Click **Run** to enable it
5. You should see a new **"Push to GitHub"** button in your toolbar

### Step 4: First Time Setup 🎯

1. **Click the "Push to GitHub" button** in Fusion 360
2. **Select "🆕 Set up new GitHub repository..."** from the dropdown (already selected on first use)
3. **Fill in the repository details:**
   - **Repository Name**: Your local name (auto-filled from URL if empty)
   - **GitHub URL**: `https://github.com/YOUR_USERNAME/YOUR_REPO_NAME`
   - **Local Folder**: Choose where to store files locally (e.g., `C:\Projects\MyDesigns`)
4. **Optional (Windows)**: Expand **Advanced**, check **Use Stored Token**, then click **Manage Token…**
5. **Click OK** to save the repository and run the export workflow

### Step 5: Export Your First Design 🎉

1. **Open a design** in Fusion 360
2. **Click "Push to GitHub"** button
3. **Configure export settings:**
   - **Format**: Keep default (Fusion Archive) or choose STEP/STL
   - **Subfolder**: Use default or customize
   - **Commit Message**: Describe your changes
4. **Click "OK"**
5. **Wait for success message**
6. **Check your GitHub repository** - your design is now backed up!

---

## 🔍 What Just Happened?

When you exported your design, the add-in:

1. **Exported** your design to the specified format
2. **Created a new git branch** with timestamp
3. **Added files** to your local repository
4. **Committed changes** with your message
5. **Pushed** everything to GitHub
6. **Updated a changelog** tracking your design history

Your design is now safely stored in GitHub with full version history!

---

## 🎮 Try These Next Steps

### Experiment with Different Formats
- Try exporting as **STEP** for CAD compatibility
- Export as **STL** for 3D printing
- Use **F3D** format to preserve full Fusion history

### Explore Branch Templates
- Change branch template to `features/{filename}-{timestamp}`
- Try `releases/v{timestamp}` for release versions
- Use `experiments/{filename}` for trying new ideas

### Use the Changelog
- Enable changelog to track design evolution
- Review `CHANGELOG.md` in your repository
- Share design history with collaborators

---

## ❓ Common Questions

**Q: Where are my exported files stored?**
A: Locally in the path you specified, and automatically synced to GitHub.

**Q: Can I use this with private repositories?**
A: Yes! Just make sure your PAT has access to private repos.

**Q: What if I make mistakes?**
A: Everything is version controlled - you can always go back to previous versions.

**Q: Can others collaborate on my designs?**
A: Yes! Share your GitHub repository and they can access all versions.

**Q: Does this cost money?**
A: The add-in is free. GitHub has free plans with unlimited public repositories.

---

## 🆘 Need Help?

If something isn't working:

1. **Check the logs**: Expand **Logging** and click **Open Log File…**
2. **Run the tests**: from the downloaded project folder, run `python tests/test_runner.py`
3. **Verify prerequisites**: Make sure Git and GitHub access work
4. **Review troubleshooting**: See `TROUBLESHOOTING.md` for common issues

---

## 🎯 What's Next?

Now that you're set up:

- **Read the User Guide** (`USER_GUIDE.md`) for detailed features
- **Try the Quick Reference** (`QUICK_REFERENCE.md`) for keyboard shortcuts
- **Explore Advanced Features** like branch override and custom templates
- **Set up team collaboration** by sharing repositories

**Congratulations!** You now have professional-grade design backup and version control for your Fusion 360 projects! 🎉