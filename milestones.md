# FusionToGitHub Add-In Roadmap

This roadmap turns the current refinement backlog into a sequence of actionable milestones. Each milestone lists its objective, concrete tasks, success criteria, and any notable dependencies or resources.

---

## Milestone 1 – Dialog UX Polish
- Key events appear in Fusion's text console for quick scanning. *(Met – Fusion palette handler mirrors log entries.)*
- One-click access to the rotating log file works on Windows and macOS. *(Met – View Log button opens log file in default editor.)*stones. Each milestone lists its objective, concrete tasks, success criteria, and any notable dependencies or resources.

---

## Milestone 1 – Dialog UX Polish

**Status**
: ✅ Completed – initial dialog UX polish merged (Sept 28, 2025).

**Objective**
: Reduce friction in the command dialog so common workflows require fewer clicks and feel more guided.

**Key Tasks**
- Group related inputs into collapsible sections (Repo, Export, Git Messaging) and add inline help tooltips for placeholders like `{filename}`.
- Dynamically toggle visibility of "New Repo" fields when `+ Add new GitHub repo...` is selected instead of keeping them always on screen.
- Persist last-used repo selection and commit message between sessions (e.g., via cached config keys).

**Success Criteria**
- Returning users can launch the dialog and push with no manual re-entry of default values.
- Usability feedback (self-test or user) confirms the form feels less cluttered and more understandable.

**Dependencies / Notes**
- Relies on existing config storage (`~/.fusion_git_repos.json`).
- Ensure Fusion UI handlers cleanly refresh when fields are shown/hidden.

---

## Milestone 2 – Repository Configuration Ergonomics

**Status**
: ✅ Completed – repository selection UX, validation, and path picker delivered (Sept 28, 2025).

**Objective**
: Make configuring repositories safer and more intuitive, especially for first-time setup.

**Key Tasks**
- Provide real-time validation indicators for repo path, git URL, and presence of `.git` directory instead of modal-only errors.
- Add a "Browse" picker to select local repo folders, storing absolute paths.
- Cache loaded config for the lifetime of the command execution to avoid redundant file reads.

**Success Criteria**
- Invalid inputs surface clear inline feedback before submission.
- Users can select an existing local repo without typing paths manually.
- Profiling/logging shows config reads drop to one per command invocation.

**Dependencies / Notes**
- Builds on Milestone 1 UI structure.
- Consider thread safety if expanding to async validation (keep on main thread for now).

---

## Milestone 3 – Export Pipeline Robustness

**Status**
: ✅ Completed – export validation, per-format settings, and temp lifecycle delivered (Oct 2, 2025).

**Objective**
: Ensure exports succeed (or fail gracefully) across supported formats while keeping the repo clean.

**Key Tasks**
- Check prerequisites (drawings/sketches) before attempting DWG/DXF; collect warnings into a single summary message. *(Done – dialog now validates and surfaces warnings prior to export.)*
- Introduce per-format settings (e.g., STL refinement, STEP protocol) via secondary dialogs, persisting overrides in repo config. *(Done – new format settings table with repo-scoped persistence.)*
- Wrap temp directory lifecycle in context management to guarantee cleanup on any exit path. *(Done – ephemeral export directories use a context manager.)*

**Success Criteria**
- Export attempts produce a single consolidated status message (success with summary or aggregated warnings). *(Met – warnings surface once, exports abort cleanly when none apply.)*
- Advanced settings persist per repo and apply on subsequent exports. *(Met – settings round-trip in config and apply during export.)*
- Temp directories are absent after both successful and failed runs (verify via logging or manual inspection). *(Met – context manager ensures cleanup.)*

**Dependencies / Notes**
- Requires config schema updates; document in Milestone 7. *(Follow-up: add schema note + screenshot update in docs.)*
- Coordinate with Milestone 4 to ensure new files are tracked appropriately.

---

## Milestone 4 – Git Flow Resilience

**Status**
: ✅ Completed – git flow resilience features integrated into the add-in (Sept 30, 2025).

**Objective**
: Harden git interactions to handle common edge cases (dirty working tree, rebase conflicts, auth hurdles) with clear guidance.

- Add user prompts when local changes are stashed or when rebase fails, including a "Skip pull (force push)" advanced checkbox.
- Preview generated branch names and allow last-minute edits while keeping token support (`{filename}`, `{timestamp}`).
- Integrate optional HTTPS PAT storage via OS credential manager (Windows Credential Manager/macOS Keychain) for smoother authentication.
- Allow exports to target configurable subfolders within the repository for better organisation.

**Success Criteria**
- Logging shows informative messages for stash/pull events; users understand what happened without checking logs. *(Met – auto-stash operations logged with clear messaging.)*
- Branch names can be customized pre-push and still adhere to safe character rules. *(Met – branch preview override implemented in dialog.)*
- Authenticating with PAT once enables subsequent pushes without re-entering credentials on supported OSes. *(Met – PAT storage workflow implemented via Windows Credential Manager.)*
- Exports can be redirected to per-repo subfolders without polluting the repo root, and changelog entries reflect the nested paths. *(Met – export subfolder support added with path normalization.)*

**Dependencies / Notes**
- Depends on Milestone 2 validation for repo path accuracy.
- PAT storage security considerations documented in README with implementation details.

---

## Milestone 5 – Observability & Error Reporting

**Status**
: 🚧 In progress – foundational logging exists but dialog controls are still outstanding (last reviewed Sept 29, 2025).

**Objective**
: Make diagnosing issues fast by exposing richer logging controls and easy access to log outputs.

**Key Tasks**
- Mirror critical log entries to Fusion’s text command palette to reduce modal spam.
- Add log-level selector (Info/Warn/Error) in the dialog, persisted per repo or globally.
- Provide a "View Log" button that opens `PushToGitHub.log` in the default editor.

**Success Criteria**
- Users can raise or lower log verbosity without code edits. *(Not met – no dialog control yet.)*
- Key events appear in Fusion’s text console for quick scanning. *(Not met – log entries currently stay in the file only.)*
- One-click access to the rotating log file works on Windows and macOS. *(Not met – button not present.)*

**Dependencies / Notes**
- Coordinate UI placement with Milestone 1 layout changes.
- Ensure logger handlers remain singleton to avoid duplicates when re-running the command.

---

## Milestone 6 – Packaging & Dependency Strategy

**Status**
: ✅ Completed – packaging baseline and CLI harness shipped (Sept 29, 2025).

**Objective**
: Simplify installation and contribution by formalizing dependency handling and distribution artifacts.

**Key Tasks**
- Decide on GitPython vendoring vs. pure CLI approach; update code and docs accordingly. *(Done – standardized on the Git CLI and documented zero external deps.)*
- Add `requirements.txt` (or `pyproject.toml`) and a simple CLI harness for offline testing. *(Done – empty `requirements.txt` plus `push_cli.py` harness using the shared core.)*
- Populate `version` in `Push_To_GitHub.manifest` and align with `VERSION` constant in Python. *(Done – both bumped to V7.7.)*

**Success Criteria**
- Fresh installs no longer require manual `pip install GitPython` unless intentionally chosen. *(Met – dependency section now highlights CLI-only strategy.)*
- Contributors can run lint/tests outside Fusion using the new manifest files. *(Met – CLI harness drives git operations without Fusion.)*
- Manifest version increments alongside code releases. *(Met – manifest and script versions now in sync at 7.7.)*

**Dependencies / Notes**
- Coordinate with Milestone 7 documentation updates.
- If vendoring dependencies, verify Autodesk distribution guidelines.

---

## Milestone 7 – Documentation & Onboarding

**Objective**
: Provide clear guidance for new users and contributors, reflecting functionality added in earlier milestones.

**Key Tasks**
- Update README with dialog screenshots/GIFs, a quick-start checklist, and examples of commit/branch placeholders.
- Document the config file schema, advanced export settings, and PAT storage workflow.
- Add a CHANGELOG template snippet demonstrating the automatic entry format.

**Success Criteria**
- README covers installation, configuration, and troubleshooting in a single pass.
- Users can understand config JSON fields without reading source code.
- Documentation references all new capabilities introduced in previous milestones.

**Dependencies / Notes**
- Should follow completion of Milestones 1–6 to capture accurate behavior.
- Consider adding localization-ready strings if future internationalization is desired.

---

## Cross-Milestone Considerations

- **Testing:** After each milestone, smoke-test core flows (export + push) on both Windows and macOS if available. Consider adding automated tests via the CLI harness (Milestone 6).
- **Versioning:** Increment the `VERSION` constant and manifest version once significant functionality lands; tag releases in GitHub for discoverability.
- **Feedback Loop:** Capture user feedback after Milestones 1, 3, and 4 to validate UX and git flow assumptions before proceeding.
