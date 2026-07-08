# Release Notes Draft (unreleased)

## Title
FusionToGitHub — Reliability Overhaul: Correct Pushes, Working Setup, Safer Credentials

## Summary
A full audit of the add-in found and fixed critical bugs in the push
pipeline, the new-repository flow, and credential handling. Every fix is
covered by automated regression tests that run in CI on Windows and Linux.

## Highlights

### Push pipeline correctness (critical fixes)
- Exports are now committed exactly as exported: previously the auto-stash
  could swallow first-time exports (push failed) or silently push **stale**
  file content while reporting success.
- Pull-rebase conflicts no longer leave the repository mid-rebase with
  changes stranded in the stash; failed pulls are aborted cleanly and any
  restore problem is reported with recovery instructions.
- Cancelling a prompt is now reported as a cancellation, not a failure.

### New-repository setup that works
- Setting up from a GitHub URL now clones the remote (or creates an
  initial commit), so the first push succeeds on brand-new repositories.
- Repository name can be left blank — it is derived from the URL.
- Missing git identity (user.name/user.email) is detected up front and
  requested inside Fusion instead of failing with a git error.

### Branching
- "Branch Name Override" is opt-in and blank by default; the second push
  no longer collides with the first push's branch name.
- Explicitly reusing an existing branch appends a commit after
  confirmation; auto-generated names uniquify on collision.

### Security
- The Personal Access Token is no longer written to disk by the askpass
  helper; credentials pass through environment variables only.

### Platform & UX
- The add-in now loads on macOS (Windows-only import was unguarded).
- Export subfolders support `{filename}` and `{timestamp}` placeholders.
- Dialog stays open with your input intact after any error.
- Removed the DWG/DXF export options — Fusion's design export API does
  not support them and they never produced files.
- Toolbar icon shrunk from 1.8 MB to 75 KB.

### Docs & quality
- README rewritten for non-programmer Fusion users.
- 17 automated tests (including end-to-end git pipeline scenarios) run in
  CI on Ubuntu and Windows across Python 3.10–3.12; lint is clean.

## Validation
- `python tests/test_runner.py` → 17/17 pass.
- `ruff check src/ tests/` → clean.
- Manual smoke test inside Fusion 360 recommended before tagging
  (dialog open → toggle formats → push).
