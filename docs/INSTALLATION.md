# FusionToGitHub Installation Guide

## 📋 System Requirements

### Required Software
- **Autodesk Fusion 360** (Personal or Commercial license)
- **Git** (2.20 or later recommended)
- **Windows 10/11** or **macOS 10.15+**
- **GitHub account** (free or paid)

### System Specifications
- **RAM**: 4GB minimum (8GB+ recommended for large designs)
- **Storage**: 500MB free space for add-in and local repositories
- **Network**: Internet connection for GitHub synchronization

---

## 🛠️ Step 1: Install Prerequisites

### Install Git

**Windows:**
1. Download Git from: https://git-scm.com/downloads
2. Run the installer with these important settings:
   - ✅ **"Git from the command line and also from 3rd-party software"**
   - ✅ **"Use Windows' default console window"**
   - ✅ **"Enable Git Credential Manager"**
3. Complete installation and restart your computer

**macOS:**
1. **Option A**: Download from https://git-scm.com/downloads
2. **Option B**: Install via Homebrew: `brew install git`
3. **Option C**: Install Xcode Command Line Tools: `xcode-select --install`

**Verify Installation:**
Open command prompt/terminal and run:
```bash
git --version
```
Should display: `git version 2.x.x`

### Create GitHub Account

1. Go to https://github.com
2. Sign up for free account (or use existing account)
3. Verify your email address

### Generate Personal Access Token (PAT)

1. **Login to GitHub** → Click profile picture → **Settings**
2. **Developer settings** (bottom of left sidebar)
3. **Personal access tokens** → **Tokens (classic)**
4. **Generate new token (classic)**
5. **Configure token**:
   - **Note**: "FusionToGitHub Add-in"
   - **Expiration**: Choose appropriate duration (90 days recommended)
   - **Scopes**: Select **repo** (Full control of private repositories)
6. **Generate token** and **copy immediately** (you won't see it again!)
7. **Save token securely** (password manager recommended)

---

## 📦 Step 2: Download FusionToGitHub

### Option A: Download Release (Recommended)
1. Go to the GitHub repository
2. Click **Releases** on the right side
3. Download latest version as ZIP file
4. Extract ZIP to temporary location

### Option B: Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/FusionToGitHub.git
cd FusionToGitHub
```

---

## 📁 Step 3: Install Add-in Files

### Locate Fusion 360 Add-ins Directory

**Windows:**
1. Press `Windows + R`
2. Type: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
3. Press Enter

**macOS:**
1. Open Finder
2. Press `Cmd + Shift + G`
3. Enter: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
4. Click Go

### Install Files

1. **Create folder**: `FusionToGitHub` in the AddIns directory
2. **Copy add-in runtime files** into this folder (from the repository `src/` directory):
   ```
   FusionToGitHub/
   ├── Push_To_GitHub.py
   ├── Push_To_GitHub.manifest
   ├── fusion_git_core.py
   ├── dialog_helpers.py
   └── push_cli.py
   ```

   Documentation and test files can remain in your project workspace; they do not need to be copied into the Fusion add-in runtime folder.

### Verify File Permissions (Windows)

1. **Right-click** each Python file (.py)
2. Select **Properties**
3. If you see **"Unblock"** checkbox, check it and click **OK**
4. Repeat for all .py files

---

## 🚀 Step 4: Enable Add-in in Fusion 360

### First-time Setup

1. **Start Fusion 360**
2. Go to **UTILITIES** tab in ribbon
3. Click **ADD-INS** button
4. Click **Scripts and Add-Ins** panel
5. Find **"Push to GitHub (ZAC)"** in list
6. Click **Run** to enable the add-in
7. **Optional**: Check **"Run on Startup"** for automatic loading

### Verify Installation

1. Look for **"Push to GitHub"** button in toolbar
2. If not visible, check **UTILITIES** tab
3. Button should show GitHub icon

---

## ⚙️ Step 5: Configure First Repository

### Create Test Repository

1. **Go to GitHub** → Click **"+"** → **New repository**
2. **Repository name**: `fusion-test-repo`
3. **Description**: "Test repository for FusionToGitHub add-in"
4. **Public** or **Private** (your choice)
5. ✅ **Add a README file**
6. Click **Create repository**

### Configure Add-in

1. **Click "Push to GitHub"** button in Fusion 360
2. **Select "+ Add new GitHub repo..."**
3. **Fill in details**:
   - **Repository Name**: `fusion-test-repo` (auto-filled from URL if left empty)
   - **GitHub URL**: `https://github.com/YOUR_USERNAME/fusion-test-repo`
   - **Local Folder**: `C:\Projects\fusion-test-repo` (Windows) or `/Users/YOUR_USERNAME/Projects/fusion-test-repo` (macOS)
4. ✅ **Optional (Windows)**: Expand **Advanced** and enable **Use Stored Token**
5. **Click "Manage Token…"** if you want to store/update a PAT in Credential Manager
6. **Click "OK"** to save and execute

### Clone Repository Locally

The add-in can initialize the local repository, but you can also do it manually:

```bash
# Navigate to parent directory
cd "C:\Projects" # Windows
cd "/Users/YOUR_USERNAME/Projects" # macOS

# Clone repository
git clone https://github.com/YOUR_USERNAME/fusion-test-repo.git
```

---

## 🧪 Step 6: Test Installation

### Run Automated Tests

1. **Open command prompt/terminal**
2. **Navigate to add-in folder**:
   ```bash
   cd "%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToGitHub" # Windows
   cd "~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionToGitHub" # macOS
   ```
3. **Run tests**:
   ```bash
   python test_runner.py
   ```
4. **Expected result**: All tests should pass (7/7)

### Test Basic Export

1. **Create simple design** in Fusion 360 (or use existing)
2. **Click "Push to GitHub"** button
3. **Select your test repository**
4. **Configure export**:
   - **Format**: Fusion Archive (.f3d)
   - **Commit message**: "Test export from installation"
5. **Click "OK"**
6. **Wait for success message**
7. **Check GitHub repository** - should see new files and commit

---

## ✅ Step 7: Verify Complete Installation

### Checklist

- [ ] Git installed and accessible (`git --version` works)
- [ ] GitHub account created and accessible
- [ ] Personal Access Token generated and saved
- [ ] Add-in files copied to correct Fusion 360 directory
- [ ] Add-in appears in Fusion 360 Scripts and Add-Ins
- [ ] "Push to GitHub" button visible in toolbar
- [ ] Test repository created on GitHub
- [ ] Repository configured in add-in and saved successfully
- [ ] Automated tests pass (7/7)
- [ ] Test export completed successfully
- [ ] Files appear in GitHub repository

### If Everything Works

🎉 **Congratulations!** Your FusionToGitHub installation is complete.

**Next steps**:
1. Read `GETTING_STARTED.md` for first-time usage
2. Review `USER_GUIDE.md` for complete features
3. Keep `QUICK_REFERENCE.md` handy for daily use

---

## 🚨 Troubleshooting Installation Issues

### Add-in doesn't appear

**Check**: File locations and permissions
**Solution**: Review Step 3, ensure files are in correct AddIns folder

### Git not found errors

**Check**: Git installation and PATH
**Solution**: Reinstall Git with command-line option enabled

### Authentication fails

**Check**: Personal Access Token validity and permissions
**Solution**: Generate new PAT with `repo` scope

### Connection test fails

**Check**: Network connectivity and repository URL
**Solution**: Verify GitHub URL format and repository accessibility

**For detailed troubleshooting**: See `TROUBLESHOOTING.md`

---

## 🔄 Updating the Add-in

### When Updates Available

1. **Download new version** (same as Step 2)
2. **Close Fusion 360** completely
3. **Replace files** in add-in folder
4. **Restart Fusion 360**
5. **Test with automated tests**

### Preserve Settings

Your repository configurations are stored separately and won't be lost during updates.

---

## 🗑️ Uninstalling

### Complete Removal

1. **Close Fusion 360**
2. **Delete add-in folder**:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToGitHub`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionToGitHub`
3. **Optional**: Remove stored credentials from Windows Credential Manager
4. **Optional**: Keep local Git repositories for manual use

---

*Installation complete! For usage instructions, see `GETTING_STARTED.md` or `USER_GUIDE.md`.*