# Security

FusionToGitHub is a local Autodesk Fusion add-in. It has **no server, no
account system, and makes no calls to the GitHub API**. Everything it does is
run the `git` command-line tool that is already installed on your machine. This
document describes exactly how it handles your GitHub credentials, and how to
report a problem.

If anything here does not match what the code does, that is a bug — please
report it (see [Reporting](#reporting-a-problem)).

---

## How authentication actually works

There are two paths, and the add-in picks one automatically:

### 1. Default: your system Git handles sign-in (browser / device flow)

If you do **not** turn on "Use Stored Token", the add-in runs `git push` with no
credential handling of its own. Git then authenticates the way it always does —
through **Git Credential Manager (GCM)**, which ships with Git for Windows and
Git for macOS:

- The **first** time you push, GCM opens a **browser window** (or offers a
  **device code**) to sign in to GitHub.
- GCM stores the resulting credential itself, in the OS keychain — on Windows
  that is a Windows Credential Manager entry named `git:https://github.com`; on
  macOS it is the login Keychain.
- Later pushes reuse that cached credential with no prompt.

This entry is created and owned by **Git**, not by this add-in. The add-in never
sees it.

### 2. Optional (Windows only): a Personal Access Token you store yourself

In the dialog's **Advanced** section, **Use Stored Token** + **Manage Token…**
let you paste a GitHub Personal Access Token (PAT). When this is on:

- The token is written to **Windows Credential Manager** as a *Generic*
  credential named `FusionToGitHub::<repository-name>` (one per configured
  repository), persisted for the local machine. Your GitHub username is stored
  alongside it. This is done with the Win32 `CredWriteW` API in
  `src/Push_To_GitHub.py` (`store_pat`).
- On each push, the add-in reads that entry (`read_stored_pat`) and hands the
  token to Git through an **ephemeral askpass helper**
  (`src/fusion_git_core.py`, `git_askpass_env`):
  - A throwaway script (`askpass.bat` / `askpass.sh`) is written to a fresh
    temp directory. **The script contains no credentials** — it only echoes two
    environment variables.
  - Those variables (`FUSION_GIT_ASKPASS_TOKEN`, `FUSION_GIT_ASKPASS_USERNAME`)
    exist **only in the environment of that one `git` subprocess**. The token
    is never written to a file.
  - `GIT_TERMINAL_PROMPT=0` is set so Git can never fall back to an interactive
    prompt.
  - When the push finishes (success or failure), the script and its temp
    directory are **deleted** in a `finally` block.

The offline test harness `src/push_cli.py` also accepts `--pat-token` on the
command line. That is for testing with a **throwaway** token only — a real token
on a command line ends up in your shell history and the process list. Do not use
it with a token you care about.

### What the add-in never does

- It never calls `api.github.com` and never runs any OAuth flow of its own.
- It never creates the GitHub repository for you — you create it on github.com
  first, and the add-in clones / initialises it locally.
- It never writes your token to its config file, its log file, the repository,
  or the commit history (see [Where credentials must never go](#where-credentials-must-never-go)).

---

## Least privilege: which token to use

Because the token is handed to Git as an ordinary HTTPS password, **GitHub
accepts both fine-grained and classic PATs**. Prefer fine-grained.

### Fine-grained PAT (preferred)

GitHub → *Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token*:

- **Resource owner:** your account (or the org that owns the repo).
- **Repository access:** *Only select repositories* → pick just the repo(s) you
  back up with this add-in.
- **Permissions:** **Repository permissions → Contents → Read and write**. That
  is the only permission a push needs. (`Metadata: Read-only` is added
  automatically.)
- **Expiration:** set the shortest that is practical for you and renew it.

Do **not** grant `Administration`, `Workflows`, `Secrets`, `Actions`, or any
account/organization permission — the add-in uses none of them.

### Classic PAT (only if fine-grained is unavailable)

Some organisations still restrict fine-grained tokens. If you must use a classic
token, the minimum scope is **`repo`**. Be aware this is broad: it grants access
to **every** repository your account can reach, not just the one you back up.
Set an expiration.

---

## Where credentials must never go

A GitHub token is a password. Keep it out of anything that can be shared,
committed, or logged:

- **Repository files or committed configuration.** Never put a token in a file
  in the repo, in `.git/config`, or in a remote URL like
  `https://TOKEN@github.com/you/repo.git`. Use the add-in's Manage Token…
  dialog (or GCM) instead — those store it in the OS credential vault, outside
  git.
- **Commit messages and branch templates.** These are user-editable in the
  dialog and are written into history and into `CHANGELOG.md`. Keep tokens out
  of them.
- **The log file.** The add-in writes `~/.PushToGitHub_AddIn_Data/PushToGitHub.log`
  and by design never logs the token. If you ever see a token in that file,
  that is a security bug — report it and revoke the token.
- **The config file.** `~/.fusion_git_repos.json` holds repository paths, URLs,
  and a `useStoredPat` on/off flag — never the token itself. Keep it that way.
- **Screenshots and screen shares.** The Manage Token… prompt shows the token
  as **visible text** while you type it (Fusion's dialog API has no masked
  field). Do not paste a token while sharing your screen or recording.
- **Issue reports.** When filing a bug, attach the log file and your OS / Fusion
  / Git versions — never a token, and never a private design file.

If a token is exposed anywhere, **revoke it on GitHub immediately** (below) and
issue a new one.

---

## Deleting vs. revoking a token

These are different actions and you usually want both:

| Goal | Action |
|------|--------|
| Stop this add-in using the stored token | Dialog → Advanced → **Manage Token… → Delete token**. This removes the `FusionToGitHub::<repo>` entry from Windows Credential Manager. It does **not** touch anything on GitHub. |
| Fully invalidate the token everywhere | GitHub → *Settings → Developer settings → Personal access tokens* → delete the token. Any copy of it, anywhere, immediately stops working. |
| Clear the *browser sign-in* credential (path 1 above) | Windows: *Credential Manager* → remove `git:https://github.com`. macOS: *Keychain Access* → remove the `github.com` internet password. Or run `git credential-manager github logout`. |

When you rotate or lose a token, do the GitHub revocation first, then clean up
the local copies.

---

## Reporting a problem

**There is no private reporting channel for this project right now.** GitHub
"Private vulnerability reporting" is not enabled on the repository and there is
no published security contact address.

- If the issue is **not sensitive** (a crash, a confusing message, a wrong
  permission recommendation): open a normal
  [issue](https://github.com/zcohen-nerd/FusionToGitHub/issues) and put
  `security` in the title. Do not include a token or a private design file.
- If the issue **is sensitive** (for example, a way the token could be leaked to
  disk or logs): open a minimal issue that says only *"security issue, details
  withheld — please enable private vulnerability reporting"* with **no
  technical detail**, and wait for the maintainer to open a private channel.

*Maintainer note:* enabling **Settings → Security → Private vulnerability
reporting** would provide a proper channel with no address to maintain; this
file should then be updated to point at the repository's Security tab.

## Expectations

Single maintainer, best-effort, no guaranteed response time, no bug bounty.
Confirmed security fixes are noted in the release notes. The software is
provided without warranty (see [`LICENSE`](LICENSE)).
