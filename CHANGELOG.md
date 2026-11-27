# Changelog

All notable changes to the FusionToGitHub add-in. Versions follow
[semantic versioning](https://semver.org/). The version is defined once, in
`src/Push_To_GitHub.manifest` (the file Fusion and the Community Store read).
`VERSION` in `src/fusion_git_core.py`, the README and the top heading of this
file must match it; `scripts/check_release.py` and the `T_VERSION` test enforce
this, and the release workflow refuses a tag that differs.

## 0.5.0 — Unreleased

**A testable add-in, safer settings, and repository Edit/Remove.**

### Added

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
  must run on Fusion's main thread and a Git-only part, ready for a
  background thread in a later release.

### Removed

- Copilot-specific agent and prompt files in `.github/`; development
  instructions for every contributor stay in `CONTRIBUTING.md`.

### Quality

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
