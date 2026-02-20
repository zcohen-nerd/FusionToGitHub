# Release Notes Draft

## Title
FusionToGitHub - UX Cleanup and Workflow Reliability Improvements

## Summary
This update makes the Fusion 360 push workflow cleaner, faster, and easier to use for day-to-day work, while also improving reliability and maintainability behind the scenes.

## Highlights

### Cleaner Dialog UX
- Simplified and standardized field labels throughout the dialog.
- Moved **Commit Message** to top-level so the common flow is quicker.
- Collapsed low-frequency groups by default: **Templates**, **Advanced**, and **Logging**.
- Smart-collapsed **Export Formats** for returning users.
- Hid new-repo-only path/status controls when an existing repo is selected.
- Added repo-name auto-fill from pasted GitHub URL.

### Engineering Improvements
- Refactored dialog helper logic into `src/dialog_helpers.py`.
- Tightened exception handling and validation paths.
- Added CI workflow under `.github/workflows/ci.yml`.
- Fixed agent prompt/schema issues for Copilot workflow files.
- Updated milestones consistency.
- Switched project license to MIT.

## Validation
- Syntax check passed for `src/Push_To_GitHub.py`.
- Automated tests passed: `tests/test_runner.py` -> 7/7.

## Commit
- `0a1343cb538dfea90f743829f0fdb7071b94e87b`
- Message: *Clean up Fusion dialog UX and stabilize workflows*

## Changed Files
- `.github/agents/principal-software-engineer.agent.md`
- `.github/agents/se-technical-writer.agent.md`
- `.github/prompts/suggest-awesome-github-copilot-agents.prompt.md`
- `.github/workflows/ci.yml`
- `LICENSE`
- `milestones.md`
- `src/Push_To_GitHub.py`
- `src/dialog_helpers.py`