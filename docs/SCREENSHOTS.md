# Screenshots

The documentation and the store listings need screenshots of the add-in in
**real Fusion**. None has been taken yet. Screenshots must be captured in
Fusion itself: never a mock-up, and never the simulated Fusion used by the
tests. Until they exist, the documentation describes each screen in words.

## How to capture them

- In Fusion on Windows, with the release candidate installed, using a test
  repository and a design that contains nothing private (no customer names, no
  real repository or account names that shouldn't be public).
- Light theme, 100 % display scale, unless the row says otherwise.
- PNG, cropped to the window or panel, at most 2000 × 2000 pixels and 1 MiB
  (Community Store limit: 1 MiB, 4096 px).
- Save them in `docs/images/` with the file name below, and record the Fusion
  build and the date in this table.

## Needed

| File name | Shows | Used in | Captured |
|---|---|---|---|
| `dialog-first-backup.png` | The dialog set up for a first backup: *Set up a new GitHub repository…*, an address pasted, *What changed?* filled in, Back up now enabled | README (Your first backup), user guide | Not yet |
| `dialog-everyday.png` | The dialog for a saved repository, with *Saves to* visible | README (Everyday use), user guide | Not yet |
| `dialog-disabled.png` | Back up now greyed out, with the "Before backing up: …" line | User guide, troubleshooting | Not yet |
| `dialog-advanced.png` | The Advanced section expanded | User guide | Not yet |
| `check-my-setup.png` | A Check My Setup report | User guide, troubleshooting | Not yet |
| `progress.png` | The progress window with Cancel during a backup | User guide | Not yet |
| `summary-success.png` | The success summary with the Open on GitHub question | README, user guide | Not yet |
| `error-network.png` | A failed backup message (network off) | Troubleshooting | Not yet |
| `toolbar-light.png`, `toolbar-dark.png` | The button in the ADD-INS panel, light and dark theme | Installation guide, branding | Not yet |
| `addins-list.png` | Utilities → Add-Ins with Push to GitHub, Run and Run on Startup | Installation guide | Not yet |
| `github-folder.png` | A design's folder on GitHub with HISTORY.md | Restore guide | Not yet (can be captured on github.com with a test repository) |
| `github-history.png` | A file's History on GitHub | Restore guide | Not yet (github.com) |

When the store screenshots exist, add up to six of them to
`community-store.json` (`"screenshots": ["docs/images/….png", …]`); the
Community Store shows the first on the add-in's card.
