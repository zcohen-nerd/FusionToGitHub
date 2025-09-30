# FusionToGitHub Installation - Organized Repository

## Quick Installation Guide

### For Fusion 360 Add-in Installation

1. **Download/Clone** this repository
2. **Copy the `src` folder contents** to your Fusion 360 add-ins directory:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToGitHub\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionToGitHub/`

3. **Required files for Fusion 360**:
   ```
   FusionToGitHub/
   ├── Push_To_GitHub.py         # Main add-in file
   ├── Push_To_GitHub.manifest   # Add-in manifest
   ├── fusion_git_core.py        # Core git operations
   └── push_cli.py               # CLI harness (optional)
   ```

4. **Enable the add-in** in Fusion 360:
   - UTILITIES → ADD-INS → Scripts and Add-Ins
   - Find "Push to GitHub (ZAC)" and click Run

### For Development/Testing

If you want to run tests or develop the add-in:

1. **Clone the full repository** with organized structure
2. **Run automated tests**:
   ```bash
   python tests/test_runner.py
   ```
3. **Read documentation**:
   - Start with `docs/GETTING_STARTED.md`
   - Complete setup: `docs/INSTALLATION.md`

### Repository Structure

```
FusionToGitHub/
├── src/                          # Source code (copy to Fusion)
├── docs/                         # Complete documentation
├── tests/                        # Testing framework
├── assets/                       # Icons and assets
└── README.md                     # Project overview
```

For complete installation instructions, see [docs/INSTALLATION.md](docs/INSTALLATION.md).