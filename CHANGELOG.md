# Changelog

All notable changes to the FusionToGitHub add-in, in the spirit of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/): newest first, grouped
by kind of change, with contributors credited. Versions follow
[semantic versioning](https://semver.org/). The version is defined once, in
`src/Push_To_GitHub.manifest` (the file Fusion and the Community Store read).
`VERSION` in `src/fusion_git_core.py`, the README and the top heading of this
file must match it; `scripts/check_release.py` and the `T_VERSION` test enforce
this, and the release workflow refuses a tag that differs.

## 0.8.0 — Unreleased

**Documentation rewritten and consolidated, community files, and the
Community Store listing icon.**

Development version; not published. 0.4.0 remains the current release;
these notes add to 0.6.0's and 0.7.0's.

### Added

- **A backup and restore guide** ([docs/RESTORE.md](docs/RESTORE.md)):
  what a backup contains, finding a version with `HISTORY.md` or a file's
  History, downloading it, opening it in Fusion, designs with linked
  components, and getting backups from the local folder if GitHub isn't
  available.
- **One installation guide** ([docs/INSTALL.md](docs/INSTALL.md)):
  requirements, the release ZIP and the Community Store, macOS, updating in a
  running Fusion, going back to an earlier version (including how to bring
  back settings for 0.4.0 and earlier), two copies, and a complete uninstall
  list.
- **Community files:** [SUPPORT.md](SUPPORT.md), a
  [Code of Conduct](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1), issue
  forms for bug reports and feature requests, and a pull request template.
- **`community-store.json`**, so the Fusion Community Store shows the
  add-in's icon. [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md) lists the
  screenshots still to be taken in real Fusion.
- **Documentation checks:** CI now fails on destructive commands, the old
  `FusionToGitHub` install folder, "Fusion 360" outside a file path, and
  hard-coded test counts.

### Changed

- **README rewritten**: what the add-in does and doesn't do, before you
  start, install, first backup, everyday use, getting an old version back,
  limits, platform support, help, and a trademark notice. "Automatic" is
  gone from the tagline: backups happen when you click.
- **User guide and troubleshooting rewritten** for 0.7.0's dialog: every
  option, what happens on a backup, where backups go, and every message the
  add-in shows with its fix. Every fix is safe; none discards work.
- **[Teams](docs/TEAMS.md)** replaces the team guide: an honest account of
  what works with several people and one repository, and what doesn't.
- "Autodesk Fusion" throughout (not "Fusion 360", except in folder paths).
  Labels in messages match the dialog ("Use stored token", "Help & Privacy").
- [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md) updated for
  0.7.0: per-repository name and email, the per-command credential file, the
  design marker, current function names.

### Removed

- Superseded documents: `INSTALL_QUICK.md`, `docs/INSTALLATION.md`,
  `docs/GETTING_STARTED.md`, `docs/QUICK_REFERENCE.md`,
  `docs/DOCUMENTATION_INDEX.md` (replaced by [docs/README.md](docs/README.md)),
  `docs/TEAM_GUIDE.md`, `docs/RELEASE_NOTES_DRAFT.md`,
  `TROUBLESHOOTING_CRASHES.md`, `REFACTORING_SUMMARY.md`, `milestones.md`,
  `tests/MANUAL_TESTS.md` and `tests/TEST_FRAMEWORK_SUMMARY.md`. Their
  current content is in the documents above; the old versions are in Git
  history. `tests/TESTING.md` now describes the current test suites.

## 0.7.0 — Unreleased

**One running history by default, a simpler dialog that explains itself,
Check My Setup, links to the backup on GitHub, and the add-in's own icon.**

Development version; not published. 0.6.0 is also unpublished, so 0.4.0
remains the current release, and these notes add to 0.6.0's.

### Added

- **One running history (new repositories).** A repository set up with this
  version adds every backup to one history on the repository's main branch,
  with each design in its own folder under `designs/` (for example
  `designs/Bracket/`). The folder always shows the latest version, and its
  `HISTORY.md` lists every backup. Advanced → *Backup branch* keeps the
  backups on a branch of their own instead (for example `fusion-backups`);
  Advanced → *Separate branch per backup* restores the snapshot branches of
  earlier versions.
- **Open on GitHub and Copy Link.** After a backup the summary says where it
  went (branch and folder), the commit, the Fusion version and the files,
  and offers to open the design's folder on GitHub or copy the link.
- **Check My Setup** (in the Repository section) checks Git and its
  version, your name and email, the GitHub sign-in helper, the repository
  folder and its address, and then tests the connection to GitHub without
  changing anything. Each result says what to do next. With no saved
  repository yet, problems that would stop a first backup (such as Git
  missing) are reported as soon as the dialog opens.
- **Fusion version in the history.** The summary and `HISTORY.md` record
  which Fusion version of the design was backed up, and whether it had
  unsaved changes (the dialog also says so before you back up).
- **The add-in's own icon:** an isometric cube with an orange branch, on
  the toolbar button (16 and 32 px, with high-resolution versions), in
  Fusion's Scripts and Add-Ins list and for store listings. It replaces the
  earlier icon, which contained GitHub's logo. The icons are generated from
  one vector drawing (`scripts/make_icons.py`, see `branding/README.md`).

### Changed

- **OK is "Back up now" and stays disabled** until everything needed is
  filled in; a line under the files says what is missing, in plain words.
- **"What changed?" is required and starts empty** every time, instead of
  repeating the previous message. New repositories title each commit
  "<design>: <what changed>"; repositories saved earlier keep their commit
  template.
- **A simpler dialog.** The basic view shows the design (and its Fusion
  version), the repository, where the backup will go, "What changed?" and
  the files to include, each described ("STEP (.step): for other CAD
  programs"). History options, branch and folder settings, the commit
  format and the stored token moved to **Advanced**; logs and the privacy
  policy to **Help & Privacy**. "Set up a new GitHub repository…" is now
  the last entry of the repository list, and returning users start on
  their saved repository.
- **Plain-language errors.** Every error shown in Fusion starts with what
  went wrong and what to do next (sign-in refused, repository not found,
  no internet connection, a protected branch, a file too large for GitHub,
  another Git program using the folder, …), with Git's own message kept
  underneath as technical details. Python tracebacks are never shown in a
  dialog any more; they go to the log file only.
- **Design folders are checked against GitHub.** Each design's `HISTORY.md`
  now carries a hidden marker (a hash of the design's Fusion id, not the id
  itself). Before a backup, the add-in looks at the folders already on
  GitHub, so two saved repositories (or two computers) pushing different
  designs with the same name get different folders, and a design finds its
  own folder again (risk R-24).
- The toolbar button is shown on the toolbar by default but no longer
  forced there: moving it into the ADD-INS menu is respected (audit
  COMP-13). The tooltip says what the command does.

### Security

- **The stored token is no longer in any process environment** (risk
  R-21, E4). For each Git command that needs it, the token is written to a
  private file that exists only while that command runs; Git's credential
  helper reads it from there. Programs Git starts, environment listings and
  crash dumps no longer contain it. Tested with a synthetic token against a
  local HTTPS server.

### Removed

- **The STEP AP203/AP214 option.** Fusion's STEP export has no such
  setting, so the option did nothing (audit BUG-03). A saved choice is
  ignored.

### Upgrading

- Repositories saved by earlier versions **keep their snapshot branches**
  and settings; nothing is migrated. To switch one to a running history,
  untick Advanced → *Separate branch per backup*.

### Quality

- Fusion's simulated API now disables OK while `validateInputs` says the
  inputs aren't valid, and every dialog test fails if a traceback reaches a
  message box. New tests cover the error catalog, the links, Check My
  Setup, the history modes, the design-folder markers (against real Git)
  and the icons (the committed files must match the generator).

## 0.6.0 — Unreleased

**Pushes run in the background, exports are checked, updates work without
restarting Fusion, and a testable add-in with safer settings and repository
Edit/Remove.**

0.5.0 was never released on its own: its changes (developed as sprint S3)
ship in this release together with sprint S4's.

### Added

- **Fusion stays usable during a push.** The Git part of a push runs on a
  background thread, and the dialog closes as soon as the push starts.
  Progress, questions and the result are shown on Fusion's main thread; the
  background thread never calls Fusion. Only one push runs at a time.
- **Cancel a push.** The progress window's Cancel button stops Git
  straight away. The message then says truthfully whether anything reached
  GitHub: nothing pushed, pushed before the cancel took effect, only an
  empty repository's first commit, or couldn't tell.
- **Linked components are detected.** Fusion's API can only export `.f3d`,
  which may not include components linked from other designs. When a design
  has linked components the add-in names them and asks before pushing, and
  records a note in the design's `HISTORY.md` if you push anyway.
  **Known limitation:** such a backup may not restore on its own, and
  restoring one hasn't been verified yet; keep the linked designs in Fusion.
- **STL: one file per body** (Format Settings → STL files), with predictable
  names such as `Bracket - Arm 1 - Pin.stl`, including bodies inside
  components and bodies with the same name.
- **STL files are written in millimetres** on Fusion builds that support
  choosing the unit; on older builds a note says they use the design's
  units.
- A note when the repository folder is inside OneDrive, Dropbox, Google
  Drive, iCloud Drive or Box (sync apps can interfere with Git). Pushing is
  still allowed.
- **Edit and Remove saved repositories.** Rename a saved repository, change
  its GitHub address or local folder, or remove it. Removing only forgets the
  entry: the local folder, the GitHub repository and its history are never
  touched, and a stored token is only deleted if you say so. A rename keeps
  the stored token. Moving a repository to another server or folder turns
  off "Use Stored Token" until you turn it back on. Edits and removals are
  all-or-nothing: if one step fails, nothing changes.
- **A stored token is tied to its server.** When you save a token, the
  add-in records which server it is for (for example `github.com`), and
  refuses to use it if the repository's address points anywhere else, even
  after a rename, a folder change or re-adding a removed repository. Tokens
  saved by earlier versions are tied to their repository's server the first
  time they are used.

### Changed

- **All or nothing exports.** Every chosen format must export and pass
  basic file checks (exists, not empty, the right kind of file, under
  100 MB, no two files overwriting each other) before anything is pushed. If
  one fails, nothing is pushed and `HISTORY.md` isn't changed. Previously a
  failed format was skipped. These checks don't prove a file opens in CAD
  software. (Formats this add-in can't export at all, such as DWG/DXF from
  older settings, are still left out with a note, as before.)
- **File and folder names work on every system.** Design and body names
  are made safe the same way on Windows and macOS: characters Windows
  doesn't allow become `_`, Windows device names (`CON`, `NUL`, …) get a
  `_`, trailing dots and spaces are removed, and names that differ only in
  case get " (2)".
- **Hooks don't run during a push with a stored token**, and a repository's
  configuration can no longer start any program while the token is present
  (only https is allowed). A push with a stored token is refused if the
  repository's own `.git/config` sets a proxy or changes certificate checks,
  because those could pass the token to someone else; the message says which
  setting to remove. It is also refused if the folder's Git settings would
  send the push to a different repository than the one saved, even on the
  same server, and HTTP tracing can no longer write the token to a file or an
  error message. Pushes through Git Credential Manager are unchanged.
  See SECURITY.md.
- Design and component names are written to the commit message and
  `HISTORY.md` as a single line, so a name can't add lines there.
- New file and folder names are made with stricter rules (see below). A
  design whose name has repeated spaces, line breaks, or invisible or unusual
  Unicode characters may get a slightly different file name than in earlier
  versions; its folder is kept, because folders are remembered per design.
- Git is found in more places: an explicit `FUSION_TO_GITHUB_GIT` setting,
  Homebrew on macOS (before the Xcode placeholder), and per-user and GitHub
  Desktop installs on Windows.
- **The dialog closes when the push starts.** Errors and the result appear
  as messages when the push finishes; open the dialog again to retry. Every
  question that can be asked up front (including the one for exports over
  50 MB) is asked before the push starts, with the dialog still open.
- The add-in's modules import each other only within the add-in's own
  package, and the add-in no longer adds its folder to Python's search path.
- **Each design gets its own folder and `HISTORY.md`.** New pushes put a
  design's files, and a history of its pushes, in a folder named after the
  design (for example `Bracket/Bracket.step` and `Bracket/HISTORY.md`). The
  folder keeps its name if you rename the design in Fusion, and a different
  design with the same name gets `Bracket (2)`. An Export Subfolder setting
  becomes the parent folder. The shared `CHANGELOG.md` that earlier versions
  wrote stays where it is, unchanged, and each new history file points to it.
- **Your Git name and email are saved for the repository, not for your whole
  computer.** When Git doesn't know who you are, the add-in asks once and
  remembers the answer for that saved repository. It no longer writes your
  global Git configuration, unless you choose "all repositories" when asked.
  Nothing is written into the repository's own `.git/config`.
- **Settings are versioned and safer.** Saves are atomic (an interrupted save
  can't leave a half-written file, and is completed on the next start); a
  file that can't be read is kept as a `.corrupt-<date>` copy instead of being
  replaced; settings from 0.4.0 and earlier are converted automatically, with
  the original kept once as `.fusion_git_repos.json.v0-backup`; a file from a
  newer version opens read-only.
- Log files hide tokens and passwords in error tracebacks too, and error
  messages shown in Fusion never include them.
- **Internal structure.** The 2,000-line dialog file is split into modules
  for the Fusion entry point, the dialog, exports, logging, the push
  workflow, settings and tokens. The workflow is separated into a part that
  must run on Fusion's main thread and a Git-only part, which is what now
  runs in the background.

### Removed

- Copilot-specific agent and prompt files in `.github/`; development
  instructions for every contributor stay in `CONTRIBUTING.md`.

### Fixed

- **Updating in a running Fusion** (Community Store update, Stop → replace →
  Run, or going back to an earlier version) could fail to start the new
  version, because modules of the previous version stayed loaded.
  Reported and reproduced by DiegoV71 (#11).
- A second copy of the add-in no longer adds a second toolbar button; it
  shows a warning instead.

### Quality

- The simulated Fusion objects used by the tests are stricter: they hold
  event handlers weakly as Fusion does, refuse UI calls from other threads,
  and deliver custom events only through a simulated message loop. Tests
  use real background threads for ordering, questions, timeouts,
  cancellation and shutdown.
- Same-process updates are tested with the real 0.3.3 and 0.4.0 releases:
  the reported failure is reproduced, and updating and rolling back between
  them and 0.6.0 works.
- Not yet verified in real Fusion: see the manual checklist, sections I–M.
- The dialog is tested automatically against simulated Fusion objects, as
  are settings, tokens and the push workflow. CI also runs every suite under
  an unusual Git configuration (`tests/hostile.gitconfig`), checks that no
  temporary folders are left behind, and enforces a coverage minimum for
  every module, along with a check that every test asserts something.
- A formal [risk register](docs/RISK_REGISTER.md) and a short
  [manual Fusion checklist](tests/MANUAL_CHECKLIST.md) for each release.

## 0.4.0 — 2026-11-27

**Pushes no longer touch your local repository folder.**

### Changed

- **New push pipeline.** Each export is committed with Git plumbing in a
  temporary index, on top of the branch's latest version *on GitHub*, then
  pushed with a plain fast-forward push. The add-in no longer stashes, pulls,
  switches branches, creates local branches or copies exports into the local
  folder. Your uncommitted work, other branches and stashes are untouched
  whether a push succeeds, fails or is cancelled.
- **Snapshot branches start from GitHub's `main`**, not from whatever branch
  the local folder had checked out, so unpushed local commits can never be
  published by accident.
- **If someone pushes at the same moment**, the export is rebuilt on their
  latest version and pushed again (up to 3 attempts) instead of failing. Their
  commits are always kept.
- **Branch Name Override** checks the branch on GitHub, not locally, and asks a
  distinct question when the branch is the repository's main branch.
- **Empty repositories** get a first commit on `main` with a `.gitattributes`
  file, so text-based CAD formats are never line-ending converted.
- **Setup** no longer re-points a folder that is already connected to a
  different GitHub repository without asking, and no longer creates an empty
  local commit.
- `push_cli.py` gains `--mode single` (one running history on one branch) and
  `--target-branch`. The add-in's dialog still uses snapshot branches; choosing
  the mode in the dialog comes in a later release.

### Fixed

- **No more indefinite freezes.** Every Git call has a time limit (10 minutes
  for network steps, including a GitHub sign-in window; 1 minute for local
  ones) and never waits for terminal input. A stopped call ends the whole
  process tree, including credential helpers and hooks.
- **Non-ASCII names** (for example "Łukasz" or "Halterung für Motor") no
  longer break Git output on Windows: output is always read as UTF-8.
- **Size limits**: exports of 100 MB or more are refused before anything is
  pushed; exports over 50 MB need confirmation.
- Option-like and invalid branch names (`-n`, `a..b`, `x.lock`) are cleaned up
  or refused, and export paths can't point outside the repository.
- The history file (`CHANGELOG.md` in the repository) keeps its existing line
  endings and bytes.

### Security and privacy

- **Stored token, scoped.** A token saved with **Manage Token…** is now
  offered only to the repository's own server, only over https, and only to
  the Git commands that talk to it. Git's other credential helpers (including
  Git Credential Manager) are switched off for those commands, so they can't
  save a copy or answer with an old credential. This replaces the askpass
  script.
- **Masked token entry.** **Manage Token…** shows a password field in the
  dialog instead of a box that displayed the token.
- **No tokens in addresses.** Setup refuses a repository address with a
  password or token in it, and a push warns if an existing repository's
  address contains one. Passwords and GitHub tokens are hidden in the log and
  in error messages.
- **Privacy policy** ([PRIVACY.md](PRIVACY.md)): no telemetry; what is sent to
  the repository and stored locally; how to delete it. Linked from the new
  **Logging & Privacy** section, which also has **Clear Log**.
- **First-push notice.** Before the first push to each repository, the add-in
  explains that the design is published there and is public if the
  repository is.
- On macOS, the settings file and logs are readable only by your account.
- `push_cli.py` no longer takes a token on the command line; use the
  `FUSION_TO_GITHUB_TOKEN` environment variable or `--pat-prompt`.
- [SECURITY.md](SECURITY.md) is rewritten to match the code.

## 0.3.3 — 2026-11-27

**Safety and installability release. Supersedes the withdrawn 0.3.2.** This is
the first release with an installable ZIP attached.

### Removed

- **Force push.** The "Force Push (skip pull)" option could overwrite other
  people's commits on GitHub. It was saved per repository, so once ticked it
  applied to every later push. The option, its saved setting, both "force-push
  instead?" prompts and the CLI's `--skip-pull` flag are gone. A saved setting
  from an older version is ignored and deleted on the next push. If GitHub has
  commits your branch doesn't, the push is now refused and nothing on GitHub
  changes.

### Fixed

- **First-run setup with a blank name.** "Set up new GitHub repository..." with
  the name left blank cloned into one folder but pushed from another, so the
  first push failed with "not a Git repo" and saved the wrong folder.
- **Install instructions** named the add-in folder `FusionToGitHub`; Fusion
  needs it to match the add-in files, `Push_To_GitHub`. The install docs now
  start from the release ZIP, and explain how to upgrade a manual install.
- **Troubleshooting** no longer suggests commands that can discard work
  (`git reset --hard`, committing conflict markers, force-push).

### Changed

- The button and dialog are named **Push to GitHub** (was "Push to GitHub
  (ZAC)"). The internal command ID is unchanged, so toolbar placement is kept.
- **Releases** are built by CI from the tagged commit: the ZIP
  (`Push_To_GitHub-<version>.zip`) is reproducible, validated, given a build
  provenance attestation, and attached to a *draft* release that is published
  only after review. A tag whose version doesn't match the manifest, or that
  fails CI, never produces a release.
- The ZIP contains only what Fusion needs. The developer tools `push_cli.py`
  and `diagnostic.py` stay in the repository but are no longer shipped.
- The add-in has a stable ID (`a9902311-5949-4d34-9ea6-3d4e6250d4a9`, from
  #12), so the Community Store can recognise and update it.

### Thanks

- **@DiegoV71** reported the missing installable release (#11), added the
  stable add-in ID and the release ZIP layout (#12), and aligned the version
  and package for 0.3.3 (#14).

## 0.3.2 — Withdrawn

Tag `0.3.2` was published on 2026-11-26 from a branch that hadn't been merged.
Packaging failed because its manifest still said 0.3.1, so the release has no
installable file. It is marked as a pre-release and superseded by 0.3.3. The
tag is kept unchanged; don't install from it.

## 0.3.1 — 2026-08-31

**Reliability and consistency release.**

> **Correction (0.3.3):** this entry originally said "No functional change to
> the add-in." That was wrong. 0.3.1 contains 59 commits since 0.3, including
> these fixes to the push pipeline and setup:
>
> - Exported files enter the repository only after the auto-stash and pull
>   steps, so the stash can no longer swallow them or commit stale copies.
> - A failed `pull --rebase` is aborted, so the repository is never left
>   mid-rebase.
> - Colliding branch names get a numeric suffix instead of failing, and a
>   reused override branch is updated from GitHub first.
> - Git runs in the C locale, so message matching works on non-English
>   systems.
> - "Set up new" derives the repository name from the URL when it is left
>   blank; export subfolders accept `{filename}` and `{timestamp}`.
> - The stored-token (askpass) helper answers username and password prompts
>   correctly.
> - The manifest declares an add-in (0.3 declared a script), plus an offline
>   CLI harness, automated tests and CI.

The add-in now reports **one** version everywhere it is visible — the runtime
`VERSION` constant, the Fusion add-in manifest, `push_cli.py --version`, the
UI/log load banner, the docs, and the Git tag all read `0.3.1`.

- **Version consolidation.** Earlier `main` carried an internal `V7.7` label
  that never matched the public `0.3` tag/release; the `0.3` tag snapshot's
  runtime and manifest also disagreed with parts of its own documentation. All
  product/test/doc references to the old label are removed and a new `T_VERSION`
  test enforces cross-surface consistency. **The immutable `0.3` tag is not
  moved or rewritten** — `0.3.1` is the first internally consistent release,
  cut from the commit where every surface agrees.
- **`push_cli.py --version`** added.
- **README** — the "keeps every version forever / nothing is ever overwritten"
  language is rephrased: a successful push creates Git history, and this add-in
  never rewrites or deletes it, but Git history can still be force-pushed over,
  branches or repositories deleted, or GitHub become unavailable. It is a strong
  safety net, not a permanent archive. A "History is durable, not immutable"
  note was added to *Known limits*.
- **CI** — `ruff` pinned to an exact version and the rule set made explicit in
  `ruff.toml` (ruff 0.16 broadened its default selection, which had turned the
  Lint job red with no code change). A "Docs Integrity" job checks documentation
  links/anchors. `SECURITY.md` added.
- **Tests** — the fixture credential in `test_runner.py` is now unmistakably not
  a real token.

## 0.3 — 2025-03

Tagged public release. See the GitHub release notes for `0.3`.
