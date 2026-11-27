# FusionToGitHub Troubleshooting Guide

## 🆘 Quick Problem Solver

**Before you start**: Check the add-in logs by opening the **Logging** group and clicking "Open Log File…" - this often shows exactly what went wrong.

---

## 🔧 Installation Issues

### Add-in doesn't appear in Fusion 360

**Symptoms**: No "Push to GitHub" button, add-in not in Scripts and Add-Ins list

**Solutions**:
1. **Verify file placement**:
   - Check files are in correct add-ins folder
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\Push_To_GitHub\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/Push_To_GitHub/`
   - The folder must be named exactly `Push_To_GitHub` and contain
     `Push_To_GitHub.manifest` and `Push_To_GitHub.py` directly (not inside
     another folder). An older install in a folder named `FusionToGitHub`
     should be removed; see [Upgrading](../README.md#upgrading-from-an-earlier-version).

2. **Check file permissions**:
   - Ensure files aren't blocked (Windows: right-click → Properties → Unblock)
   - Verify folder has read permissions

3. **Restart completely**:
   - Close Fusion 360 entirely
   - Wait 10 seconds
   - Restart Fusion 360

4. **Enable manually**:
   - UTILITIES → ADD-INS → Scripts and Add-Ins
   - Look for **Push to GitHub**
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
1. **Python compatibility**: the add-in runs inside Fusion's bundled Python — you do not install Python for it. The optional CLI harness and the test suite need Python 3.10+.
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

4. **Git installed somewhere unusual** (Windows):
   - The add-in looks for `git` on PATH, then at `C:\Program Files\Git\bin\git.exe`.
   - Reinstalling Git for Windows with its default options puts it there.
   - Don't edit the add-in's files: an update replaces them.

### "Authentication failed" / "Permission denied"

**Symptoms**: Can't push to GitHub, authentication errors

**Check your token** (see [SECURITY.md](../SECURITY.md) for the full guidance):
1. **Verify the token is valid**:
   - GitHub → Settings → Developer settings → Personal access tokens
   - Check it hasn't expired
   - Fine-grained token: it must include the target repo with **Contents:
     Read and write**. Classic token: it must have the **`repo`** scope.

2. **Test access without embedding the token in a URL** (never put a token in a
   remote URL — it gets written to `.git/config`):
   ```bash
   cd "C:\path\to\your\local\repo"
   git ls-remote origin
   ```
   If that prompts for a sign-in and succeeds, Git's Credential Manager is
   working. If it fails, the token/permissions are the problem.

3. **Re-enter credentials**:
   - In the add-in dialog (**Advanced**): "Manage Token…"
   - Enter a fresh token
   - Retry the export/push

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
   - If Windows Security's **Controlled folder access** or another security
     tool blocks the write, allow Fusion in that tool's settings rather than
     turning protection off

### "Access denied" / "Permission errors"

**Symptoms**: Can't write files, permission errors

**Solutions**:
1. **Check folder permissions**:
   - Ensure the repository folder isn't read-only
   - Verify your user account has write access
   - Don't run Fusion as administrator to work around this: files it creates
     then belong to the administrator and cause more permission errors later

2. **Synced folders**: if the repository is inside OneDrive, Dropbox or
   similar, files set to "online-only" can't be written. Keep the repository
   outside synced folders, or mark it "always keep on this device".

3. **Security software**: if Windows Security's **Controlled folder access** or
   antivirus blocks the write, allow Fusion in that tool's settings. Don't turn
   protection off.

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

2. **Push to a new branch**:
   - Leave "Branch Name Override" blank; the add-in then creates a new,
     uniquely named branch for every export
   - Or type a new name, adding a suffix such as `-v2`

3. **Clean up old local branches** (only ones you created and no longer need):
   ```bash
   git branch -d old-branch-name
   ```
   `-d` refuses to delete a branch with work that isn't merged anywhere.
   Deleting a branch on GitHub removes it for everyone, so check with your
   team first.

4. **Merge conflicts**: the add-in aborts a conflicted update automatically
   and leaves your repository as it was. It never commits files containing
   conflict markers. If `git status` ever says a rebase or merge is in
   progress, cancel it with `git rebase --abort` (or `git merge --abort`).

### "Your branch is behind" / "Need to pull"

**Symptoms**: Local repository out of sync with remote

**Solutions**:
1. **The add-in doesn't need your local folder to be up to date**: it builds
   every backup on GitHub's latest version, and never changes your local
   folder. To update the folder for your own use, run `git pull` there.

2. **"GitHub kept receiving other changes"**: someone else pushed to the same
   branch several times while your export was being sent. Nothing on GitHub was
   changed; click **Push to GitHub** again.

3. **"Push failed … Nothing on GitHub was changed"** with a message from
   GitHub (for example a branch protection rule): the branch doesn't accept
   direct pushes. Leave "Branch Name Override" blank to push to a new branch.

---

## 🔐 Security and Credential Issues

### "Token stored but still asks for password"

**Symptoms**: Stored PAT doesn't work, still prompted for credentials

**Solutions**:
1. **Check Credential Manager** (Windows):
   - Windows Key + R → `control /name Microsoft.CredentialManager`
   - Look for `git:https://github.com` entries
   - Remove old/conflicting entries

2. **Check which credential helper Git uses**:
   ```bash
   git config --global credential.helper
   ```
   With Git for Windows this should print `manager`. If it prints nothing or
   the old name `manager-core`, set it with
   `git config --global credential.helper manager` (or reinstall Git for
   Windows with Git Credential Manager enabled). Don't unset a helper you
   didn't set up yourself: other tools may rely on it.

3. **Re-store credentials**:
   - In add-in: Uncheck "Use Stored Token"
   - Re-check and enter PAT again

### "PAT has insufficient permissions"

**Symptoms**: Authentication works but operations fail

**Solutions**:
1. **Check token permissions** (details in [SECURITY.md](../SECURITY.md)):
   - GitHub → Settings → Developer settings → your token
   - Fine-grained: the repo is listed, with **Contents: Read and write**
   - Classic: the **`repo`** scope is selected

2. **Organization permissions**:
   - For org repositories, check org settings
   - May need additional permissions

3. **Repository access**:
   - Verify you're collaborator on private repos
   - Check repository isn't archived or disabled

---

## 🔍 Advanced Diagnostics

### Running Built-in Tests

These need a copy of the source repository (not the installed add-in):

1. **Automated tests**:
   ```powershell
   cd "path\to\FusionToGitHub"
   python tests/test_runner.py
   ```

2. **Check specific components**:
   ```powershell
   python tests/test_runner.py --category pre-install
   python tests/test_runner.py --category git-ops
   ```

3. **CLI testing**:
   ```powershell
   python src/push_cli.py --help
   ```

### Log Analysis

**Log file locations**:
- Windows: `%USERPROFILE%\.PushToGitHub_AddIn_Data\PushToGitHub.log`
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
2. **Your local folder is safe**: since 0.4.0 the add-in never changes it, so
   there is nothing to recover there. Every Git step also has a time limit, so
   a stuck push stops on its own.
3. **Versions before 0.4.0 stashed local changes** during a push. If you used
   one and a push was interrupted, look for a stash named
   `fusion_git_addin_autostash` and restore that one specifically:
   ```bash
   git status                 # if it says "rebase in progress": git rebase --abort
   git stash list
   git stash pop stash@{N}    # N = the number shown next to fusion_git_addin_autostash
   ```
   Don't use `git reset --hard`: it permanently discards uncommitted work.

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

3. **Push again**: click **Push to GitHub** again with Branch Name Override
   blank. This creates a new branch and never overwrites what is on GitHub.

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