# FusionToGitHub — Quick Install

## Install the add-in

1. Download **`Push_To_GitHub-<version>.zip`** from the **Assets** of the
   [latest release](https://github.com/zcohen-nerd/FusionToGitHub/releases/latest).
   (Not the green **Code → Download ZIP** button: that's the source code.)
2. Unzip it into your Fusion add-ins folder so that you get exactly:

   ```
   AddIns/
   └── Push_To_GitHub/
       ├── Push_To_GitHub.manifest
       ├── Push_To_GitHub.py
       ├── fusion_git_core.py
       ├── dialog_helpers.py
       ├── AddInIcon.svg
       └── LICENSE
   ```

   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\Push_To_GitHub\`
   - macOS (experimental): `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/Push_To_GitHub/`

   The folder name must be exactly `Push_To_GitHub`, the same as the
   `.manifest` and `.py` files, or Fusion won't load it.
3. Restart Fusion, then **UTILITIES → ADD-INS**, find **Push to GitHub**, and
   click **Run**.

Step-by-step instructions with screenshots-in-words, and how to upgrade from an
older manual install, are in the [README](README.md#installing-the-add-in-5-minutes).

## Install from source (developers)

Build the same ZIP CI builds, from your current commit, and unzip it as above:

```bash
python scripts/package.py build      # writes dist/Push_To_GitHub-<version>.zip
```

The package contains only the files Fusion needs. `push_cli.py` and
`diagnostic.py` are developer tools; run them from the repository instead.

Run the automated tests with `python tests/test_runner.py`. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development and release process.

## Repository structure

```
FusionToGitHub/
├── src/                          # Add-in source (packaged by scripts/package.py)
├── scripts/                      # Packaging and release checks
├── docs/                         # Documentation
├── tests/                        # Automated tests and manual test plans
└── README.md                     # Start here
```
