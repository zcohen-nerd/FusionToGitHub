# FusionToGitHub User Guide

## Table of Contents
- [Overview](#overview)
- [Basic Operations](#basic-operations)
- [Advanced Features](#advanced-features)
- [Repository Management](#repository-management)
- [Export Options](#export-options)
- [Branch & Version Control](#branch--version-control)
- [Collaboration Features](#collaboration-features)
- [Troubleshooting](#troubleshooting)

---

## Overview

FusionToGitHub integrates Autodesk Fusion 360 with GitHub to provide professional version control for your designs. This guide covers all features and workflows.

### Key Benefits
- **Automatic Backups**: Never lose design work again
- **Version History**: Track every change with timestamps
- **Team Collaboration**: Share designs and manage contributions
- **Multiple Formats**: Export to F3D, STEP, STL, DXF, and more
- **Professional Workflow**: Branch-based development like software teams

---

## Basic Operations

### Opening the Add-in

1. **Toolbar Method**: Click the "Push to GitHub" button in your Fusion 360 toolbar
2. **Menu Method**: UTILITIES tab → ADD-INS → Scripts and Add-Ins → Run "Push to GitHub (ZAC)"
3. **Keyboard**: The add-in appears in your recent commands for quick access

### The Main Dialog

The add-in dialog has several sections:

#### Repository Selection
- **Dropdown**: Choose from configured repositories
- **"+ Add new GitHub repo..."**: Configure new repositories
- **Current Selection**: Shows active repository path and status

#### Export Settings
- **Format**: Choose output format (F3D, STEP, STL, etc.)
- **Subfolder**: Organize exports in subdirectories
- **Include Changelog**: Add entries to CHANGELOG.md

#### Git Settings
- **Branch Template**: Control branch naming
- **Commit Message**: Describe your changes
- **Branch Preview**: See operations before executing

#### Credentials
- **Use Stored PAT**: Leverage Windows Credential Manager
- **Manage PAT**: Store/update Personal Access Tokens

---

## Advanced Features

### Branch Templates

Control how branches are named using templates with placeholders:

**Default Template**: `fusion-export/{filename}-{timestamp}`
- `{filename}`: Current design name
- `{timestamp}`: Current date/time (YYYYMMDD-HHMMSS)

**Example Templates**:
- `features/{filename}-{timestamp}` → `features/Bracket_V2-20250930-143022`
- `releases/v{timestamp}` → `releases/v20250930-143022`
- `work-in-progress/{filename}` → `work-in-progress/Bracket_V2`
- `{filename}/iteration-{timestamp}` → `Bracket_V2/iteration-20250930-143022`

### Branch Preview Mode

Enable preview to see what the add-in will do without executing:

1. **Check "Branch Preview"** in the dialog
2. **Click "Export & Push to GitHub"**
3. **Review the preview dialog** showing:
   - Branch name to be created
   - Files to be exported
   - Git operations planned
   - Commit message
4. **Choose to proceed or cancel**

### Log Level Controls

Adjust logging detail for troubleshooting:

- **INFO**: Basic operation messages (default)
- **DEBUG**: Detailed operation logs
- **WARNING**: Only important warnings
- **ERROR**: Only error conditions

Access via the "Advanced" section in the dialog.

### Changelog Generation

When enabled, the add-in maintains a `CHANGELOG.md` file:

```markdown
# Design History

## 2025-09-30 14:30:22 - Branch: features/Bracket_V2-20250930-143022
**Commit**: Updated bracket with reinforcement ribs
**Files**: 
- Bracket_V2.f3d
- Bracket_V2.step

## 2025-09-29 09:15:10 - Branch: features/Bracket_V1-20250929-091510
**Commit**: Initial bracket design
**Files**:
- Bracket_V1.f3d
```

---

## Repository Management

### Adding New Repositories

1. **Select "+ Add new GitHub repo..."** from dropdown
2. **Fill in details**:
   - **GitHub URL**: Full repository URL (HTTPS or SSH)
   - **Local Path**: Where to store files locally
   - **Personal Access Token**: GitHub authentication

#### GitHub URL Formats
- **HTTPS**: `https://github.com/username/repository-name`
- **SSH**: `git@github.com:username/repository-name.git`

#### Local Path Guidelines
- Use absolute paths: `C:\Projects\MyDesigns`
- Avoid spaces in paths when possible
- Ensure write permissions
- Path will be created if it doesn't exist

### Repository Validation

The add-in validates repositories in real-time:

- ✅ **Green**: Repository is valid and accessible
- ⚠️ **Yellow**: Warning (e.g., dirty working directory)
- ❌ **Red**: Error (e.g., invalid path, no git repository)

### Stored Credentials

**Windows Credential Manager Integration**:
- Credentials stored securely by Windows
- Per-repository credential management
- Automatic authentication for HTTPS repositories
- Manage via "Manage PAT..." button

**Setting up PAT storage**:
1. Check "Use stored PAT"
2. Click "Manage PAT..."
3. Enter your GitHub Personal Access Token
4. Credentials are saved for future sessions

---

## Export Options

### File Formats

#### Fusion Archive (.f3d)
- **Best for**: Complete design preservation
- **Contains**: Full feature history, parameters, timeline
- **Use when**: Sharing with other Fusion users
- **File size**: Usually largest, but most complete

#### STEP (.step, .stp)
- **Best for**: CAD interoperability
- **Contains**: 3D geometry, surfaces
- **Use when**: Working with other CAD software
- **Standard**: Industry standard for CAD exchange

#### STL (.stl)
- **Best for**: 3D printing
- **Contains**: Triangle mesh geometry
- **Use when**: Preparing for 3D printing
- **Note**: No feature history or parameters

#### IGES (.iges, .igs)
- **Best for**: Legacy CAD systems
- **Contains**: 3D geometry, curves, surfaces
- **Use when**: Older CAD software compatibility

#### DXF (.dxf)
- **Best for**: 2D drawings, laser cutting
- **Contains**: 2D sketch geometry
- **Use when**: Manufacturing 2D parts

### Export Subfolders

Organize your exports using subfolder patterns:

**Static Folders**:
- `exports/` - All exports in one folder
- `step-files/` - Format-specific organization
- `versions/v1.0/` - Version-based organization

**Dynamic Folders** (using placeholders):
- `{filename}/` - Separate folder per design
- `exports/{timestamp}/` - Time-based organization
- `formats/{format}/` - Organize by file format

**Nested Organization**:
- `projects/{filename}/exports/`
- `releases/v{timestamp}/{format}/`
- `work/{filename}/iterations/`

---

## Branch & Version Control

### Understanding Git Workflow

The add-in follows professional Git practices:

1. **Stash**: Local changes are temporarily saved
2. **Pull**: Latest changes from GitHub are downloaded
3. **Branch**: New branch created for your export
4. **Export**: Design files are generated
5. **Add**: Files are staged for commit
6. **Commit**: Changes are committed with your message
7. **Push**: Branch is uploaded to GitHub
8. **Restore**: Any stashed changes are restored

### Branch Naming Best Practices

**Feature Branches**:
- `feature/{filename}-{timestamp}` - New features
- `feature/bracket-reinforcement` - Descriptive names

**Release Branches**:
- `release/v{timestamp}` - Version releases
- `release/production-ready` - Release candidates

**Experiment Branches**:
- `experiment/{filename}-{timestamp}` - Testing ideas
- `experiment/alternative-design` - Design alternatives

**Personal Branches**:
- `{username}/{filename}-{timestamp}` - Personal work
- `zac/bracket-improvements` - Individual contributions

### Working with Existing Branches

If you want to continue work on an existing branch:

1. **Use Branch Override**: Enter exact branch name
2. **Local Checkout**: The add-in will switch to that branch
3. **Append Changes**: New commits added to existing branch
4. **Force Push**: May be required if branch exists remotely

---

## Collaboration Features

### Team Repository Setup

**For Repository Owners**:
1. Create GitHub repository
2. Add team members as collaborators
3. Share repository configuration details
4. Establish branch naming conventions

**For Team Members**:
1. Clone repository locally
2. Configure add-in with repository details
3. Use consistent branch templates
4. Follow team commit message guidelines

### Sharing Designs

**Method 1: Direct Repository Access**
- Add collaborators to GitHub repository
- Everyone uses same repository configuration
- All exports go to shared repository

**Method 2: Fork & Pull Request**
- Team members fork main repository
- Work in personal forks
- Submit pull requests for review

**Method 3: Branch-based Collaboration**
- Use descriptive branch names
- Create pull requests for major changes
- Review changes before merging

### Version Coordination

**Avoiding Conflicts**:
- Use different branch templates per team member
- Coordinate on major design changes
- Communicate before major exports

**Review Process**:
1. Export to personal branch
2. Create pull request on GitHub
3. Team reviews changes
4. Merge after approval

---

## Troubleshooting

### Common Issues and Solutions

#### "Git executable not found"
**Problem**: Add-in can't find Git
**Solutions**:
- Install Git from git-scm.com
- Restart Fusion 360 after Git installation
- Check that `git --version` works in command prompt

#### "Authentication failed"
**Problem**: Can't push to GitHub
**Solutions**:
- Verify Personal Access Token is valid
- Check PAT has `repo` scope permissions
- Re-enter credentials via "Manage PAT..."
- Ensure GitHub URL is correct

#### "Repository not found"
**Problem**: Local repository doesn't exist or isn't valid
**Solutions**:
- Verify local path exists and is writable
- Check if `.git` folder exists in local path
- Initialize repository manually: `git init` in local folder
- Clone repository if it exists remotely

#### "Export failed"
**Problem**: Fusion export doesn't complete
**Solutions**:
- Ensure design is saved and active
- Check export format is supported
- Verify sufficient disk space
- Try different export format

#### "Merge conflicts"
**Problem**: Local and remote changes conflict
**Solutions**:
- Use fresh branch names
- Pull latest changes before exporting
- Resolve conflicts manually in Git
- Use branch preview to avoid conflicts

### Getting Help

**Built-in Diagnostics**:
1. **View Log**: Click button in add-in dialog
2. **Run Tests**: Execute `python test_runner.py`
3. **Check Git Status**: Verify repository state

**Log File Locations**:
- **Windows**: `%APPDATA%/.PushToGitHub_AddIn_Data/PushToGitHub.log`
- **macOS**: `~/.PushToGitHub_AddIn_Data/PushToGitHub.log`

**Community Support**:
- Review documentation files
- Check GitHub repository issues
- Follow troubleshooting guides

---

## Best Practices

### Repository Organization
- Use descriptive repository names
- Organize with consistent subfolder structure
- Keep repositories focused on related designs
- Document your naming conventions

### Export Workflow
- Save designs before exporting
- Use meaningful commit messages
- Export regularly to maintain history
- Test with branch preview for complex changes

### Team Collaboration
- Establish branch naming conventions
- Use descriptive commit messages
- Review changes before merging
- Communicate major design decisions

### Security
- Keep Personal Access Tokens secure
- Use repository-specific PATs when possible
- Regularly review GitHub access permissions
- Don't share credentials in commit messages

---

*This user guide covers the complete FusionToGitHub workflow. For quick reference, see `QUICK_REFERENCE.md`. For installation help, see `GETTING_STARTED.md`.*