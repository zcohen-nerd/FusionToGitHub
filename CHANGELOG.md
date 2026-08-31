# Changelog

All notable changes to the FusionToGitHub add-in. Versions follow
[semantic versioning](https://semver.org/); the single source of truth for the
version string is `VERSION` in `src/fusion_git_core.py`, and CI
(`tests/test_runner.py`, `T_VERSION`) fails if any other surface drifts from it.

## 0.3.1 — 2026-08-31

**Corrective release. No functional change to the add-in.**

The add-in now reports **one** version everywhere it is visible — the runtime
`VERSION` constant, the Fusion add-in manifest, `push_cli.py --version`, the
UI/log load banner, the docs, and the Git tag all read `0.3.1`.

- **Version consolidation.** Earlier `main` carried an internal `V7.7` label
  that never matched the public `0.3` tag/release, and the two `0.3` and
  `0.3.1` tag snapshots created before this release contained inconsistent
  internal metadata. All product/test/doc references to the old label are
  removed; a new `T_VERSION` test enforces cross-surface consistency.
  **The immutable `0.3` and `0.3.1` tags are not moved or rewritten** — this
  release is the first internally consistent one, cut from the matching commit.
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
