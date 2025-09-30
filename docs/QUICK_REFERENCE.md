# FusionToGitHub Quick Reference

## 🚀 Essential Commands

| Action | Steps |
|--------|-------|
| **Open Add-in** | Click "Push to GitHub" button in toolbar |
| **Add Repository** | Select "+ Add new GitHub repo..." → Fill details |
| **Export Design** | Select repo → Configure settings → "Export & Push" |
| **View Logs** | Click "View Log" button in dialog |
| **Manage Credentials** | Check "Use stored PAT" → "Manage PAT..." |

---

## ⚙️ Export Formats Quick Guide

| Format | Best For | File Size | Contains |
|--------|----------|-----------|----------|
| **F3D** | Fusion users, full history | Large | Complete design |
| **STEP** | CAD software | Medium | 3D geometry |
| **STL** | 3D printing | Small | Triangle mesh |
| **DXF** | 2D manufacturing | Small | 2D sketches |
| **IGES** | Legacy CAD | Medium | Curves & surfaces |

---

## 🌿 Branch Template Examples

| Template | Result | Use Case |
|----------|--------|----------|
| `fusion-export/{filename}-{timestamp}` | `fusion-export/Bracket-20250930-143022` | Default |
| `features/{filename}` | `features/Bracket` | Feature development |
| `releases/v{timestamp}` | `releases/v20250930-143022` | Version releases |
| `{filename}/v{timestamp}` | `Bracket/v20250930-143022` | Design iterations |
| `experiments/{filename}` | `experiments/Bracket` | Testing ideas |

---

## 📁 Subfolder Organization

| Pattern | Example | Organization |
|---------|---------|--------------|
| `exports/` | `exports/Bracket.step` | All exports together |
| `{filename}/` | `Bracket/Bracket.step` | Per-design folders |
| `{format}/` | `step/Bracket.step` | By file format |
| `versions/v{timestamp}/` | `versions/v20250930/Bracket.step` | By version |

---

## 🔐 Personal Access Token (PAT) Setup

### Quick Setup
1. GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scope: **repo** (Full control of private repositories)
4. Copy token
5. In add-in: Check "Use stored PAT" → "Manage PAT..." → Paste token

### PAT Permissions Needed
- ✅ **repo** - Access repositories
- ✅ **workflow** - Update GitHub Actions (if used)
- ❌ **admin** - Not needed for basic use

---

## 📝 Commit Message Templates

| Style | Example | When to Use |
|-------|---------|-------------|
| **Descriptive** | "Updated bracket with reinforcement ribs" | Feature changes |
| **Version** | "Bracket v2.1 - improved strength" | Version releases |
| **Issue-based** | "Fixed clearance issue #123" | Bug fixes |
| **Feature** | "Added mounting holes to base plate" | New features |

---

## 🚨 Quick Troubleshooting

| Problem | Quick Fix |
|---------|-----------|
| **Git not found** | Install Git → Restart Fusion |
| **Auth failed** | Check PAT → Re-enter credentials |
| **No repository** | Verify path → Initialize with `git init` |
| **Export failed** | Save design → Check disk space |
| **Branch exists** | Use different branch name or override |

---

## 🔍 Status Indicators

| Indicator | Meaning | Action |
|-----------|---------|--------|
| ✅ **Green** | Everything OK | Proceed normally |
| ⚠️ **Yellow** | Warning/attention needed | Check details |
| ❌ **Red** | Error/blocked | Fix issue before proceeding |
| 🔄 **Processing** | Operation in progress | Wait for completion |

---

## ⌨️ Keyboard Shortcuts

| Action | Shortcut | Notes |
|--------|----------|-------|
| **Open Add-in** | Recent commands menu | After first use |
| **Tab between fields** | Tab | Navigate dialog |
| **Accept dialog** | Enter | Execute export |
| **Cancel dialog** | Escape | Close without action |

---

## 📊 Log Levels

| Level | Shows | Use When |
|-------|-------|----------|
| **ERROR** | Only errors | Production use |
| **WARNING** | Errors + warnings | Normal use |
| **INFO** | Basic operations | Default setting |
| **DEBUG** | Detailed info | Troubleshooting |

---

## 🔧 Advanced Features

### Branch Preview Mode
- **Purpose**: See operations before executing
- **How**: Check "Branch Preview" box
- **Result**: Shows preview dialog before actual operations

### Custom Export Paths
- **Relative**: `exports/step/` (inside repository)
- **Dynamic**: `{filename}/v{timestamp}/` (uses placeholders)
- **Nested**: `projects/{filename}/exports/` (deep organization)

### Git Workflow Override
- **Branch Override**: Force specific branch name
- **Skip Pull**: Don't update from remote first
- **Force Push**: Overwrite remote branch

---

## 🌐 Repository URL Formats

| Type | Format | Example |
|------|--------|---------|
| **HTTPS** | `https://github.com/user/repo` | Most common |
| **SSH** | `git@github.com:user/repo.git` | Key-based auth |
| **Clone** | Copy from GitHub's "Code" button | Guaranteed correct |

---

## 📈 Workflow Examples

### Simple Backup
1. Open design → Click "Push to GitHub"
2. Keep defaults → Enter commit message
3. Click "Export & Push to GitHub"

### Team Collaboration
1. Use branch template: `features/{filename}-{timestamp}`
2. Export to personal branch
3. Create pull request on GitHub
4. Review and merge

### Version Releases
1. Use branch template: `releases/v{timestamp}`
2. Export production-ready designs
3. Tag releases on GitHub
4. Maintain changelog

---

## 🆘 Emergency Recovery

### If Something Goes Wrong
1. **Don't panic** - everything is version controlled
2. **Check logs** - Click "View Log" for details
3. **Check Git status** - Use `git status` in repository folder
4. **Restore from stash** - Use `git stash list` and `git stash pop`

### Recovering Lost Work
- All commits are preserved in Git history
- Use GitHub web interface to browse versions
- Check `git log --oneline` for commit history
- Use `git checkout <commit>` to restore specific versions

---

*For complete details, see `USER_GUIDE.md`. For installation help, see `GETTING_STARTED.md`.*