# Several people, one repository

Push to GitHub is a backup tool. Several people can back up to the same
repository, and that works well, but it isn't a collaboration system: for
working on designs together, use Fusion's own hubs and projects. This page says
what to expect.

## What works

- **Everyone backs up to one repository.** Give each person **Write** access
  (repository **Settings → Collaborators**). Each sets the repository up once in
  their own add-in.
- **Each design has its own folder**, with its own `HISTORY.md`. The add-in
  checks the folders already on GitHub before every backup, so two people's
  different designs that happen to share a name get different folders
  (`Bracket`, `Bracket (2)`), and the same design keeps its folder whoever backs
  it up.
- **Nobody overwrites anybody.** Backups are added on top of what is on GitHub,
  never force-pushed. If two people back up at the same moment, the second
  backup is rebuilt on top of the first.
- **You can see who did what.** Each commit carries its author's Git name and
  email, and `HISTORY.md` lists every backup with its note.

## What doesn't

- **No locking and no merging.** If two people change the same design and both
  back it up, both backups are kept, one after the other; the folder shows the
  later one. Nothing combines their changes, because CAD files can't be merged
  the way text can.
- **No approval step by default.** With one running history, a backup lands on
  the branch straight away.

## Setups that work

**Simple: one shared history.** Everyone backs up to the repository's main
branch (the default). Good for small teams, and for an off-site trail of
everyone's designs.

**Reviewed: a backup branch each, pull requests into main.**
1. Protect `main` (**Settings → Branches**: require a pull request).
2. Each person sets **Advanced → Backup branch** to a branch of their own, such
   as `backups-alice`.
3. When a design is ready, open a pull request from that branch into `main`.
   GitHub shows which files changed.

If two people's branches changed the same file, GitHub reports a conflict: keep
one version (GitHub's conflict editor, or decide whose file wins). The add-in
doesn't help with this.

## Access and tokens

- Each person signs in to GitHub as themselves (Git Credential Manager does
  this), or stores their **own** token. Never share a token.
- A fine-grained token can be limited to the one repository, with **Contents:
  Read and write**: see [Stored tokens](USER_GUIDE.md#stored-tokens-windows).
- A public repository shows everyone's designs to everyone. Use a private
  repository, or an organisation's private repository, for company work.
