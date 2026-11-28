# Security

FusionToGitHub is a local Autodesk Fusion add-in. It has **no server, no
account system, no telemetry, and makes no calls to the GitHub API**. Everything
it does is run the `git` command-line tool already installed on your computer.
This document describes exactly how it handles your GitHub credentials, and how
to report a problem. What it stores and sends in general is in
[PRIVACY.md](PRIVACY.md).

If anything here does not match what the code does, that is a bug. Please
report it (see [Reporting](#reporting-a-problem)).

---

## How authentication works

There are two paths. You choose with **Use Stored Token** in the dialog's
**Advanced** section.

### 1. Default: Git signs you in (Git Credential Manager)

With **Use Stored Token** off, the add-in runs `git` with no credential handling
of its own. Git authenticates the way it always does, usually through **Git
Credential Manager (GCM)**:

- **Windows:** GCM ships with Git for Windows. The first push opens a browser
  window (or offers a device code) to sign in to GitHub. GCM keeps the result
  in Windows Credential Manager as `git:https://github.com`.
- **macOS (experimental):** GCM is **not** included with every Git install; the
  Git from Xcode's command line tools and Homebrew's `git` don't include it.
  Install GCM separately, or use SSH keys, or HTTPS will fail to sign in.
- Later pushes reuse the stored credential with no prompt.

That credential is created and owned by Git (or GCM), not by this add-in.

### 2. Optional (Windows only): a token you store yourself

**Manage Token…** shows a **Token** field that hides what you type (dots
instead of characters), plus an optional **Token Username**. **Save Token**
stores them:

- The token is written to **Windows Credential Manager** as a *Generic*
  credential named `FusionToGitHub::<repository name>`, one per configured
  repository (`store_pat` in `src/Push_To_GitHub.py`). The dialog clears the
  field right after saving.
- On each push, the add-in reads it (`read_stored_pat`) and gives it to Git
  through a **temporary credential helper** (`token_auth` in
  `src/fusion_git_core.py`):
  - The token is passed only to the commands that talk to GitHub
    (`ls-remote`, `fetch`, `push`). Local git commands never receive it.
    Since 0.7.0 it is **not in any process's environment**: for each of those
    commands the add-in writes it to a file in a new folder, the helper reads
    it from there, and when that one command ends the file is overwritten and
    deleted. Only the file's location is in Git's environment. On Windows the
    folder is in your own `%LOCALAPPDATA%\PushToGitHub\credentials` (by
    default only you, the system and administrators can open it, and it isn't
    synced), not in the temporary folder, which can be redirected to a shared
    place. On macOS and Linux it is an owner-only folder in the temporary
    folder. A folder left behind by a crash is deleted by a later push once it
    is an hour old (no Git command runs that long).
  - For those commands, every other credential helper is switched off
    (`-c credential.helper=`), so GCM or a `store` helper can't save a copy of
    the token, and a stale saved credential can't be used instead of it.
  - The helper is registered for **one host only**: the host of the
    repository's address (for example `github.com`). The token is never
    offered to any other server, even if the repository's address is changed.
  - The token is only sent over **https**. If the repository's address is
    `http://` or SSH, the push stops with an explanation.
  - `GIT_TERMINAL_PROMPT=0` is always set, so Git never waits for input.

  - **Repository hooks don't run** for those commands. Since 0.6.0 the
    add-in points `core.hooksPath` at an empty temporary folder for any Git
    command that carries the token, so a repository's own `pre-push` (or
    other) hook can't read it from the environment. If you rely on a
    `pre-push` hook, it still runs when you push from your own Git tools,
    and when the add-in pushes through Git Credential Manager (path 1),
    which passes no token to Git. Commit hooks never run: the add-in builds
    its commits with `git commit-tree`.
  - **Nothing else a repository configures runs either.** Only the https
    transport is allowed (`GIT_ALLOW_PROTOCOL=https`), so an address
    rewritten to `ext::<command>`, `file://` or SSH can't start a program.
    No askpass program is inherited, and submodules aren't fetched or pushed.
  - **A repository's own proxy or certificate settings stop the push.** If
    the repository's `.git/config` (or a file it includes) sets a proxy
    (`http.proxy`, `http.<url>.proxy`, `remote.<name>.proxy`) or changes TLS
    trust (`http.sslVerify`, `http.sslCAInfo`, client certificates, and
    similar), those settings could pass the token to someone else, so the
    add-in refuses to send it and says which setting to remove. Proxy
    settings in your *global* Git config (for example a company proxy) are
    used as normal.
  - The token goes only to the **repository** you chose. If the folder's Git
    settings would send the push anywhere else (`remote.origin.pushurl`,
    `url.*.insteadOf`), even on the same server, or to a server other than
    the one the token was saved for, the push is refused.
  - HTTP tracing you may have switched on (`GIT_TRACE_CURL`,
    `GIT_CURL_VERBOSE`) is off for these commands, and Git's redaction is
    forced on, so the token can't end up in a trace file or an error message.
  - **Known limits:** while one of those commands runs (usually seconds),
    another program running as *you* could find and read the file. Such a
    program can already read the stored token from Windows Credential Manager,
    so this isn't a new exposure (risk R-21). Other standard users can't open
    the folder, unless you have changed the permissions of your profile
    folders. Because the token is briefly on disk, its bytes may remain in
    unused disk space after deletion, and antivirus software may scan the
    file while it exists.

The developer test harness `src/push_cli.py` (not part of the installed add-in)
reads a token from the `FUSION_TO_GITHUB_TOKEN` environment variable or from a
hidden prompt (`--pat-prompt`). It never accepts one as a command-line argument,
because other programs can read a process's command line.

### What the add-in never does

- It never calls `api.github.com` and never runs an OAuth flow of its own.
- It never creates the GitHub repository for you.
- It never writes your token to its config file, its log, the repository, the
  commit history, or Git's own credential stores.
- It never accepts a repository address with a password or token in it, such
  as `https://user:TOKEN@github.com/you/repo.git`. If an existing repository's
  address already contains one, every push shows a warning explaining how to
  remove it.
- Error messages and the log hide anything that looks like a URL password or a
  GitHub token (`ghp_…`, `github_pat_…`), and the stored token itself.

---

## Least privilege: which token to use

GitHub accepts both fine-grained and classic personal access tokens. Prefer
fine-grained.

### Fine-grained token (preferred)

GitHub → *Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token*:

- **Resource owner:** your account (or the organisation that owns the repo).
- **Repository access:** *Only select repositories* → just the repositories you
  back up with this add-in.
- **Permissions:** **Repository permissions → Contents → Read and write**. That
  is the only permission a push needs. (`Metadata: Read-only` is added
  automatically.)
- **Expiration:** the shortest that is practical for you; renew it.

Don't grant `Administration`, `Workflows`, `Secrets`, `Actions`, or any
account or organisation permission. The add-in uses none of them.

### Classic token (only if fine-grained is unavailable)

The minimum scope is **`repo`** (or **`public_repo`** if every repository you
push to is public). `repo` is broad: it grants access to **every** repository
your account can reach. Set an expiration.

---

## Where credentials must never go

A GitHub token is a password. Keep it out of anything that can be shared,
committed or logged:

- **Repository files or addresses.** Never put a token in a file in the repo,
  in `.git/config`, or in a remote address. Use **Manage Token…** (or GCM)
  instead.
- **Commit messages and branch templates.** These are written into history and
  into the repository's `CHANGELOG.md`.
- **Screenshots and screen shares.** The Token field is masked, but don't paste
  a token while recording anyway.
- **Bug reports.** The log (`~/.PushToGitHub_AddIn_Data/PushToGitHub.log`)
  never contains the token, but it does contain folder paths, repository
  addresses, your Git messages and design names. **Read it and remove anything
  private before attaching it**, and never attach a private design file.

If a token is exposed anywhere, **revoke it on GitHub immediately** (below) and
create a new one.

---

## Deleting vs. revoking a token

These are different actions, and you usually want both:

| Goal | Action |
|------|--------|
| Stop this add-in using the stored token | **Advanced → Manage Token… → No (Delete it)**. This removes the `FusionToGitHub::<repo>` entry from Windows Credential Manager. It does **not** affect GitHub. |
| Make the token useless everywhere | GitHub → *Settings → Developer settings → Personal access tokens* → delete it. Every copy stops working immediately. |
| Clear the browser sign-in credential (path 1) | Windows: *Credential Manager → Windows Credentials* → remove `git:https://github.com`. macOS: *Keychain Access* → remove the `github.com` entry. Or run `git credential-manager github logout`. |

When you rotate or lose a token, revoke it on GitHub first, then clean up the
local copies.

---

## Local files

| File | Contains | Protection |
|------|----------|------------|
| `~/.fusion_git_repos.json` | Saved repositories: folder, address, formats, templates, options | Owner-only (`600`) on macOS. On Windows, your user profile folder is private to you. |
| `~/.PushToGitHub_AddIn_Data/PushToGitHub.log` (+ up to 3 older copies, 1 MB each) | What the add-in did, with folder paths, addresses and Git messages; secrets redacted | Owner-only on macOS. **Logging & Privacy → Clear Log** deletes them. |

Git hooks, filters and `core.fsmonitor` configured *in a repository* run when
the add-in runs Git there, as they do for any Git command (except hooks during
a push with a stored token, above). Only use the add-in with repositories you
trust.

---

## Reporting a problem

- If the repository's **Security** tab offers **Report a vulnerability**, use
  it: that is a private channel to the maintainer.
- Otherwise, for a **sensitive** issue (for example a way the token could leak),
  open a minimal [issue](https://github.com/zcohen-nerd/FusionToGitHub/issues)
  saying only *"security issue, details withheld; please open a private
  channel"*, with **no technical detail**, and wait for a reply.
- For anything **not sensitive** (a crash, a confusing message), open a normal
  issue with `security` in the title. Never include a token or a private
  design.

*Maintainer note:* turn on **Settings → Code security → Private vulnerability
reporting** to provide the private channel above.

## Expectations

Single maintainer, best effort, no guaranteed response time, no bug bounty.
Confirmed security fixes are noted in the release notes. The software is
provided without warranty (see [`LICENSE`](LICENSE)).
