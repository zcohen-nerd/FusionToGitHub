# Changelog

All notable changes to the FusionToGitHub add-in. Versions follow
[semantic versioning](https://semver.org/). The version is defined once, in
`src/Push_To_GitHub.manifest` (the file Fusion and the Community Store read).
`VERSION` in `src/fusion_git_core.py`, the README and the top heading of this
file must match it; `scripts/check_release.py` and the `T_VERSION` test enforce
this, and the release workflow refuses a tag that differs.

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
