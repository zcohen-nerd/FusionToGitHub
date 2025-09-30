# Autodesk Fusion to GitHub Add-In

This Fusion 360 Add-In automatically exports your Autodesk Fusion designs to GitHub with professional version control. Perfect for easy backups, team collaboration, and design history tracking.

## 📚 Complete Documentation

**New to FusionToGitHub?** Start here:

### 🚀 **[Get Started in 15 Minutes](docs/GETTING_STARTED.md)**
Quick-start guide for first-time users - from installation to your first export.

### 📖 **[Complete Documentation Index](docs/DOCUMENTATION_INDEX.md)**
Full documentation suite organized by user type and task.

### 🔧 **Key Guides**:
- **[Installation Guide](docs/INSTALLATION.md)** - Complete setup instructions
- **[User Guide](docs/USER_GUIDE.md)** - All features and workflows  
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Commands and settings cheat sheet
- **[Team Collaboration](docs/TEAM_GUIDE.md)** - Professional team workflows
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Problem resolution guide

---

## ⚡ Quick Overview

### What This Add-In Does
- **Exports** Fusion 360 designs in multiple formats (F3D, STEP, STL, etc.)
- **Commits** changes to GitHub with automatic version control
- **Creates** professional design history and changelogs
- **Manages** branches for different design iterations
- **Enables** team collaboration with Git workflows

### Key Features
- ✅ **One-click export** to GitHub repositories
- ✅ **Multiple export formats** (F3D, STEP, STL, DXF, IGES)
- ✅ **Automatic branching** with customizable naming
- ✅ **Secure credential storage** via Windows Credential Manager
- ✅ **Professional Git workflow** with stash/pull/push
- ✅ **Team collaboration** support with branch management
- ✅ **Comprehensive logging** for troubleshooting

---

## � Repository Structure

```
FusionToGitHub/
├── src/                          # Source code
│   ├── Push_To_GitHub.py         # Main Fusion 360 add-in
│   ├── Push_To_GitHub.manifest   # Add-in manifest file
│   ├── fusion_git_core.py        # Shared git operations
│   └── push_cli.py               # Offline CLI harness
├── docs/                         # Documentation
│   ├── DOCUMENTATION_INDEX.md    # Documentation navigation
│   ├── INSTALLATION.md           # Setup instructions
│   ├── GETTING_STARTED.md        # Quick start guide
│   ├── USER_GUIDE.md             # Complete feature reference
│   ├── QUICK_REFERENCE.md        # Command cheat sheet
│   ├── TEAM_GUIDE.md             # Team collaboration
│   └── TROUBLESHOOTING.md        # Problem resolution
├── tests/                        # Testing framework
│   ├── test_runner.py            # Automated test runner
│   ├── TESTING.md               # Systematic test plan
│   ├── MANUAL_TESTS.md          # Manual test checklist
│   └── TEST_FRAMEWORK_SUMMARY.md # Testing overview
├── assets/                       # Assets and icons
│   └── AddInIcon.svg             # Add-in icon
├── README.md                     # This file
├── LICENSE                       # MIT license
├── requirements.txt              # Python dependencies (empty by design)
├── milestones.md                 # Development milestones
└── .gitignore                    # Git ignore patterns
```

---

## �🚀 Quick Start

### Prerequisites
- Autodesk Fusion 360
- Git installed on your system
- GitHub account with Personal Access Token

### Installation
1. **Download** add-in files
2. **Copy** to Fusion 360 add-ins folder
3. **Enable** in Fusion 360 Scripts and Add-Ins
4. **Configure** your first repository

**Full instructions**: [docs/INSTALLATION.md](docs/INSTALLATION.md)

### First Export
1. **Click** "Push to GitHub" button in Fusion 360
2. **Configure** repository settings
3. **Choose** export format and commit message
4. **Click** "Export & Push to GitHub"

**Detailed walkthrough**: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

---

## 🔧 How It Works

### Simple Workflow
```
1. Design in Fusion 360
2. Click "Push to GitHub"
3. Configure export settings
4. Add-in exports files → Creates git branch → Commits changes → Pushes to GitHub
5. Your design is safely versioned on GitHub!
```

### What Happens Behind the Scenes
1. **Stash**: Saves any local changes temporarily
2. **Pull**: Gets latest updates from GitHub
3. **Branch**: Creates new branch with timestamp
4. **Export**: Saves design in chosen format(s)
5. **Commit**: Creates git commit with your message
6. **Push**: Uploads everything to GitHub
7. **Cleanup**: Restores any stashed changes

---

## 🎯 Use Cases

### Individual Designers
- **Automatic backups** of design iterations
- **Version history** tracking design evolution
- **Portfolio building** with organized project history
- **Format flexibility** for different use cases

### Design Teams
- **Centralized storage** for all team designs
- **Collaboration workflows** with branch management
- **Review processes** via GitHub Pull Requests
- **Conflict resolution** for simultaneous edits

### Professional Projects
- **Release management** with tagged versions
- **Change documentation** with automatic changelogs
- **Compliance tracking** with full audit trails
- **Integration** with existing development workflows

---

## 🔐 Personal Access Token (PAT) Storage

On Windows, the add-in supports secure PAT storage via Windows Credential Manager:

- **Setup**: Check "Use stored PAT" and click "Manage PAT..." to store your GitHub token securely
- **Benefits**: Eliminates repeated authentication prompts for HTTPS repositories
- **Security**: Tokens are stored using Windows' native credential system and encrypted at rest
- **Per-Repository**: Each repository can have its own stored credentials
- **Cross-Session**: Tokens persist across Fusion sessions until manually removed

---

## 🔄 Git Flow Behavior

- **Auto-stashing**: Local changes are temporarily saved before operations and restored afterward
- **Smart pulling**: Updates from remote before creating export branch
- **Branch sanitization**: Branch names are cleaned to remove unsupported characters
- **Changelog generation**: Each export creates an entry in `CHANGELOG.md`
- **Export validation**: Warnings surface in the summary dialog for review

---

## 🧪 Offline CLI Harness

The `push_cli.py` script enables testing the Git pipeline without Fusion 360:

```powershell
python push_cli.py --repo C:\path\to\repo --files exports/model.step --design-name BracketV4
```

**Features**:
- Full Git pipeline testing
- CI/CD integration support
- No additional dependencies required
- Automated validation capabilities

**Usage details**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md#offline-cli-harness)

---

## 🧪 Testing & Quality Assurance

This add-in includes a comprehensive testing framework:

### Automated Testing
```powershell
# Test all automated components
python tests/test_runner.py

# Test specific categories
python tests/test_runner.py --category pre-install
```

### Manual Testing
- **Quick Smoke Test** (3 minutes): Basic functionality validation
- **Full Manual Suite** (60 minutes): Comprehensive feature testing
- **Systematic Testing**: Professional QA with 49 test cases

**Testing details**: [tests/TESTING.md](tests/TESTING.md) and [tests/MANUAL_TESTS.md](tests/MANUAL_TESTS.md)

---

## ✅ Troubleshooting Common Issues

### Add-in Not Appearing
- Ensure files are in correct Fusion 360 add-ins folder
- Restart Fusion 360 completely
- Check file permissions (Windows: unblock files)

### Git Not Found
- Install Git from git-scm.com
- Choose "Git from command line and 3rd-party software"
- Restart computer after installation

### Authentication Failed
- Verify Personal Access Token has `repo` scope
- Re-enter credentials via "Manage PAT..."
- Check GitHub repository access permissions

**Complete troubleshooting**: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## 📈 Future Roadmap

### Planned Features
- **Bill of Materials (BOM) Export**: CSV/JSON format alongside designs
- **Project Metadata Export**: Design parameters and component information
- **Thumbnail/Image Export**: Visual references in Git history
- **Pull Request Automation**: Automatic PR creation after export
- **Drawing Export**: 2D drawings as DWG/PDF
- **Manufacturing Export**: CAM toolpaths and NC files

### Completed Milestones
- ✅ **V7.7**: Dependency packaging and offline CLI harness
- ✅ **Milestones 4&5**: Branch preview, log level controls, export subfolder support
- ✅ **Core Features**: Multi-format export, secure PAT storage, professional Git workflow

---

## 🤝 Contributing

We welcome contributions! Here's how to help:

### Reporting Issues
1. Check existing issues first
2. Include system information (OS, Fusion version, Git version)
3. Provide error messages from logs
4. Describe steps to reproduce

### Suggesting Features
1. Review planned roadmap
2. Describe use case and benefits
3. Consider implementation complexity
4. Provide examples if applicable

### Code Contributions
1. Fork the repository
2. Create feature branch
3. Follow existing code style
4. Add tests for new functionality
5. Submit pull request with clear description

---

## 📞 Support

### Self-Help Resources
- **Documentation**: Complete guides for all scenarios
- **Testing Tools**: Automated and manual validation
- **Log Analysis**: Built-in diagnostics and troubleshooting

### Community Support
- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: Community Q&A and tips
- **Documentation**: Improvements and updates

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🎉 Acknowledgments

Built for the Fusion 360 community with professional-grade version control capabilities. Special thanks to all contributors and users who have provided feedback and suggestions.

---

*Ready to get started? Check out [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for a 15-minute quick start guide!*