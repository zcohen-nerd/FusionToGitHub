# FusionToGitHub Troubleshooting Guide

## 🆘 Quick Problem Solver

**Before you start**: Check the add-in logs by clicking "View Log" in the dialog - this often shows exactly what went wrong.

---

## 🔧 Installation Issues

### Add-in doesn't appear in Fusion 360

**Symptoms**: No "Push to GitHub" button, add-in not in Scripts and Add-Ins list

**Solutions**:
1. **Verify file placement**:
   - Check files are in correct add-ins folder
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToGitHub\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionToGitHub/`

2. **Check file permissions**:
   - Ensure files aren't blocked (Windows: right-click → Properties → Unblock)
   - Verify folder has read permissions

3. **Restart completely**:
   - Close Fusion 360 entirely
   - Wait 10 seconds
   - Restart Fusion 360

4. **Enable manually**:
   - UTILITIES → ADD-INS → Scripts and Add-Ins
   - Look for "Push to GitHub (ZAC)"
   - Click "Run" if it appears

### Add-in shows errors on startup

**Symptoms**: Python errors, import failures, missing modules

**Check Python environment**:
```powershell
# Test in command prompt/terminal
python -c "import sys; print(sys.version)"
python -c "import os, subprocess, tempfile"
```

**Solutions**:
1. **Python compatibility**: Ensure Python 3.8+ is installed
2. **Module issues**: All required modules are built-in to Python
3. **File corruption**: Re-download and reinstall add-in files

---

## 🌐 Git and GitHub Issues

### "Git executable not found"

**Symptoms**: Error about git not being available

**Solutions**:
1. **Install Git**:
   - Download from: https://git-scm.com/downloads
   - Choose "Git from the command line and also from 3rd-party software"
   - Restart computer after installation

2. **Test Git installation**:
   ```powershell
   git --version
   ```
   Should show Git version number

3. **Check PATH**:
   - Ensure Git is in system PATH
   - Try `where git` (Windows) or `which git` (macOS/Linux)

4. **Manual Git path**:
   - Edit `Push_To_GitHub.py`
   - Update `GIT_EXE` variable with full path to git.exe

### "Authentication failed" / "Permission denied"

**Symptoms**: Can't push to GitHub, authentication errors

**Check Personal Access Token**:
1. **Verify PAT is valid**:
   - Go to GitHub → Settings → Developer settings → Personal access tokens
   - Check token hasn't expired
   - Ensure `repo` scope is selected

2. **Test PAT manually**:
   ```bash
   git clone https://YOUR_TOKEN@github.com/username/repository.git
   ```

3. **Re-enter credentials**:
   - In add-in dialog: "Manage PAT..."
   - Enter fresh token
   - Test connection

4. **Check repository access**:
   - Verify you have write access to the repository
   - For organization repos, check organization permissions

### "Repository not found" / "Not a git repository"

**Symptoms**: Local repository errors, can't find .git folder

**Solutions**:
1. **Initialize repository**:
   ```bash
   cd "C:\path\to\your\local\folder"
   git init
   git remote add origin https://github.com/username/repository.git
   ```

2. **Clone existing repository**:
   ```bash
   git clone https://github.com/username/repository.git "C:\path\to\local\folder"
   ```

3. **Fix remote URL**:
   ```bash
   cd "C:\path\to\repository"
   git remote set-url origin https://github.com/username/repository.git
   ```

4. **Verify repository structure**:
   - Check that `.git` folder exists in local path
   - Ensure local path points to repository root

---

## 📤 Export and File Issues

### "Export failed" / "No active design"

**Symptoms**: Can't export design files, export process stops

**Solutions**:
1. **Ensure design is active**:
   - Open a design in Fusion 360
   - Make sure design is saved
   - Verify design isn't corrupted

2. **Check export format**:
   - Try different export format (F3D, STEP, STL)
   - Some formats require specific design content

3. **Disk space**:
   - Ensure sufficient disk space for export
   - Check both local drive and temp directory

4. **File permissions**:
   - Verify write access to export directory
   - Check antivirus isn't blocking file creation

### "Access denied" / "Permission errors"

**Symptoms**: Can't write files, permission errors

**Solutions**:
1. **Run as administrator** (Windows):
   - Right-click Fusion 360 → Run as administrator
   - Only needed for troubleshooting

2. **Check folder permissions**:
   - Ensure export folder isn't read-only
   - Verify user has write access

3. **Antivirus interference**:
   - Temporarily disable antivirus
   - Add add-in folder to antivirus exclusions

4. **Path length issues** (Windows):
   - Use shorter paths (under 260 characters)
   - Avoid deep nested folder structures

---

## 🔄 Workflow and Branch Issues

### "Branch already exists" / "Merge conflicts"

**Symptoms**: Git branch errors, can't create new branch

**Solutions**:
1. **Use unique branch names**:
   - Enable timestamp in branch template
   - Use `{filename}-{timestamp}` pattern

2. **Force new branch**:
   - Use "Branch Override" with unique name
   - Try adding suffix: `-v2`, `-fixed`, etc.

3. **Clean up old branches**:
   ```bash
   git branch -d old-branch-name
   git push origin --delete old-branch-name
   ```

4. **Resolve conflicts manually**:
   ```bash
   git status
   git add .
   git commit -m "Resolve conflicts"
   ```

### "Your branch is behind" / "Need to pull"

**Symptoms**: Local repository out of sync with remote

**Solutions**:
1. **Let add-in handle it**:
   - Add-in automatically pulls before pushing
   - Don't manually intervene during process

2. **Manual sync if needed**:
   ```bash
   git pull --rebase origin main
   ```

3. **Force push** (use carefully):
   - Only if you're sure about overwriting remote
   - Enable force push in add-in settings

---

## 🔐 Security and Credential Issues

### "Token stored but still asks for password"

**Symptoms**: Stored PAT doesn't work, still prompted for credentials

**Solutions**:
1. **Check Credential Manager** (Windows):
   - Windows Key + R → `control /name Microsoft.CredentialManager`
   - Look for `git:https://github.com` entries
   - Remove old/conflicting entries

2. **Clear Git credential cache**:
   ```bash
   git config --global --unset credential.helper
   git config --global credential.helper manager-core
   ```

3. **Re-store credentials**:
   - In add-in: Uncheck "Use stored PAT"
   - Re-check and enter PAT again

### "PAT has insufficient permissions"

**Symptoms**: Authentication works but operations fail

**Solutions**:
1. **Check PAT scopes**:
   - Go to GitHub → Settings → Developer settings
   - Edit your token
   - Ensure `repo` scope is selected

2. **Organization permissions**:
   - For org repositories, check org settings
   - May need additional permissions

3. **Repository access**:
   - Verify you're collaborator on private repos
   - Check repository isn't archived or disabled

---

## 🔍 Advanced Diagnostics

### Running Built-in Tests

1. **Automated tests**:
   ```powershell
   cd "path\to\FusionToGitHub"
   python test_runner.py
   ```

2. **Check specific components**:
   ```powershell
   python test_runner.py --category pre-install
   python test_runner.py --category git-ops
   ```

3. **CLI testing**:
   ```powershell
   python push_cli.py --help
   ```

### Log Analysis

**Log file locations**:
- Windows: `%APPDATA%\.PushToGitHub_AddIn_Data\PushToGitHub.log`
- macOS: `~/.PushToGitHub_AddIn_Data/PushToGitHub.log`

**Common log patterns**:
- `ERROR`: Critical failures requiring action
- `WARNING`: Issues that might cause problems
- `Git command failed`: Git operation errors
- `Authentication failed`: Credential problems

### Manual Git Commands

**Check repository status**:
```bash
cd "C:\path\to\repository"
git status
git branch -a
git remote -v
```

**Test authentication**:
```bash
git ls-remote origin
```

**Check recent commits**:
```bash
git log --oneline -10
```

---

## 🚨 Emergency Recovery

### If Fusion 360 freezes during export

1. **Force close Fusion 360**
2. **Check repository state**:
   ```bash
   git status
   git stash list
   ```
3. **Recover stashed changes**:
   ```bash
   git stash pop
   ```
4. **Clean up incomplete operations**:
   ```bash
   git reset --hard HEAD
   ```

### If repository gets corrupted

1. **Backup current work**:
   - Copy all files to safe location

2. **Fresh clone**:
   ```bash
   git clone https://github.com/username/repository.git fresh-copy
   ```

3. **Copy work back**:
   - Move your files to fresh repository
   - Re-run add-in export

### If GitHub shows wrong files

1. **Check branch**:
   - Verify you're looking at correct branch on GitHub
   - Add-in creates new branches for each export

2. **Force refresh**:
   - Hard refresh GitHub page (Ctrl+F5)
   - Check repository network graph

3. **Re-push if needed**:
   ```bash
   git push --force-with-lease origin branch-name
   ```

---

## 📞 Getting Additional Help

### Self-Help Resources

1. **Built-in documentation**:
   - `USER_GUIDE.md` - Complete feature guide
   - `QUICK_REFERENCE.md` - Command reference
   - `TESTING.md` - Test procedures

2. **Log analysis**:
   - Always check logs first
   - Look for ERROR and WARNING messages
   - Share relevant log sections when asking for help

### Community Support

1. **GitHub Issues**:
   - Check existing issues for similar problems
   - Create new issue with:
     - Error messages from logs
     - Steps to reproduce
     - System information (OS, Fusion version, Git version)

2. **Information to include**:
   - Fusion 360 version
   - Operating system
   - Git version (`git --version`)
   - Python version (`python --version`)
   - Full error messages from logs

---

## ✅ Prevention Tips

### Avoid Common Issues

1. **Regular maintenance**:
   - Keep Git up to date
   - Refresh GitHub PATs before expiry
   - Clean up old branches periodically

2. **Good practices**:
   - Use descriptive commit messages
   - Save designs before exporting
   - Test with small designs first

3. **Environment hygiene**:
   - Don't modify files in Git folder manually
   - Keep local paths reasonably short
   - Use stable internet connection for Git operations

4. **Backup strategy**:
   - Multiple repositories for important work
   - Regular exports to maintain history
   - Local backups independent of Git

---

*This troubleshooting guide covers most common issues. For additional help, check the user guide or create a GitHub issue with detailed error information.*