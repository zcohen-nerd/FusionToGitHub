# Contributing to FusionToGitHub

Bug reports and pull requests are welcome. For a large change, please open an
issue first so we can agree on the approach.

## Development setup

You need Python 3.10+ and Git. No third-party Python packages are required to
run the add-in or its tests.

| Check | Command |
|---|---|
| Automated tests | `python tests/test_runner.py` |
| Lint | `pip install ruff==0.16.5`, then `ruff check src/ tests/ scripts/` |
| Docs links | `node .github/scripts/check-docs.mjs` |
| Release consistency | `python scripts/check_release.py` |
| Build the add-in ZIP | `python scripts/package.py build` (writes `dist/`) |

CI runs all of these on every pull request and uploads the built ZIP as a
`Push_To_GitHub-test-build` artifact you can install in Fusion.

## Pull requests

- Add or update tests for behaviour you change. The Git pipeline tests run
  against local repositories and never touch GitHub.
- For changes to the Fusion dialog, which has no automated tests yet, say in
  the PR what you checked by hand in Fusion (see
  [`tests/MANUAL_TESTS.md`](tests/MANUAL_TESTS.md)).
- Update the docs in the same PR.
- Never include tokens, private designs or unredacted logs.
- The add-in must never force-push or rewrite history on GitHub; a test
  (`T_NOFORCE`) enforces this.
- External contributions are credited in the CHANGELOG with the contributor's
  GitHub handle and the PR number.

## Releasing

The version is set **once**, in `src/Push_To_GitHub.manifest`. Releases are
cut only from commits on `main`, and nothing is published automatically.

1. **Prepare the release in a pull request.**
   - Set `"version"` in `src/Push_To_GitHub.manifest`.
   - Set `VERSION` in `src/fusion_git_core.py` and the **Version** line in
     `README.md` to match.
   - Add `## X.Y.Z — YYYY-MM-DD` at the top of `CHANGELOG.md`, with credits.
   - `python scripts/check_release.py --tag X.Y.Z` must pass.
2. **Merge it** once CI is green.
3. **Tag the merged commit** with the bare version (no `v` prefix), which is
   what Fusion and the Community Store expect:
   ```sh
   git switch main && git pull
   git tag X.Y.Z && git push origin X.Y.Z
   ```
4. **The Release workflow** runs CI on the tag, checks that the tag matches
   the manifest and is on `main`, builds and validates the ZIP, attests it,
   and creates a **draft** release with the ZIP, its `.sha256` file and notes
   from the CHANGELOG. If any step fails, no release is created.
5. **Test the drafted ZIP.** Download it from the draft, install it in Fusion
   on Windows following the README, and run the smoke checks in
   [`tests/MANUAL_TESTS.md`](tests/MANUAL_TESTS.md).
6. **Publish the draft** on GitHub. Check that the asset shows a SHA-256
   digest (`gh release view X.Y.Z --json assets`).

**If something is wrong**, delete the draft, fix it on `main`, and release the
next patch version. Never move or re-push a tag that has been pushed.

**Dry run:** *Actions → Release → Run workflow* on any branch builds and
uploads the ZIP as an artifact without creating a release. To rehearse the
whole flow, push a test tag to a fork.

**One-time repository settings** (maintainer, in GitHub settings): turn on
*Immutable releases*; add a tag ruleset that blocks updating or deleting
version tags; turn on *Private vulnerability reporting*.
