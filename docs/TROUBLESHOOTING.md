# Troubleshooting

Find the message you saw, or the symptom, and follow the fix. Start with
**Check My Setup…** in the dialog: it finds most problems and says what to do.

Every fix here is safe: none of them deletes a backup, rewrites history on
GitHub, or discards your work.

- [The add-in doesn't appear or has no button](#the-add-in-doesnt-appear-or-has-no-button)
- ["Another copy of 'Push to GitHub' is already running"](#another-copy-of-push-to-github-is-already-running)
- [Back up now is greyed out](#back-up-now-is-greyed-out)
- [Messages when a backup fails](#messages-when-a-backup-fails)
- [Stored token messages](#stored-token-messages)
- [Export messages](#export-messages)
- [Settings messages](#settings-messages)
- [Setting up a repository](#setting-up-a-repository)
- [Fusion seems busy, or the backup takes long](#fusion-seems-busy-or-the-backup-takes-long)
- [After an update, the old version still runs](#after-an-update-the-old-version-still-runs)
- [Getting help](#getting-help)

## The add-in doesn't appear or has no button

1. **Check the folder** against [Install, step 3](INSTALL.md#install-from-the-release-zip):
   `AddIns/Push_To_GitHub/Push_To_GitHub.manifest`, with no extra folder level.
2. **Check it's running** ([Install, step 4](INSTALL.md#install-from-the-release-zip)).
3. **Look in the right place.** The button is in the **ADD-INS** panel of the
   **Design** workspace. If you moved it into the panel's menu, it's there.
4. **Restart Fusion** completely.
5. **Read the log.** `.PushToGitHub_AddIn_Data/PushToGitHub.log` in your home
   folder says whether the add-in started and why not.

If Fusion says the add-in "must be loaded by Fusion as a package", the files
were run outside their `Push_To_GitHub` folder: reinstall them as above.

## "Another copy of 'Push to GitHub' is already running"

Two copies of the add-in are installed (for example one installed by hand and
one by the Community Store, or an old folder). The message names both folders.
Keep one, as described in [Install → Two copies](INSTALL.md#two-copies-installed).

## Back up now is greyed out

Something the backup needs is missing. The line under **Files to include**
says what, for example:

| It says | Do this |
|---|---|
| Describe what changed | Type a note in **What changed?** |
| Choose at least one file to include | Tick at least one file type |
| Open a Fusion design first | Open the design (not a drawing) and click the button again |
| Paste the GitHub address… | When setting up: paste the repository's address |
| …contains a password or token | Paste the plain address (`https://github.com/you/repo`) and use **Manage Token…** for a token |
| Advanced → Backup branch: … | Use a branch name without spaces or `~ ^ : ? * [ \`, for example `fusion-backups` |
| Advanced → Design folders go in: … | Use a relative folder name such as `designs`, without `..` or `< > : " | ? *` |

## Messages when a backup fails

Each message starts with what went wrong, then what to do, then Git's own
words under **Technical details** (useful in a bug report). A failed backup
normally leaves GitHub unchanged. If the message says GitHub may have received
the backup, or asks you to check, look at the repository before backing up
again.

| Message | Why | Fix |
|---|---|---|
| **GitHub didn't accept your sign-in for this repository.** | Not signed in, signed in as an account without access, or an expired or too limited token | Back up again and sign in when the GitHub window opens. With a stored token: check its expiry and that it has **Contents: Read and write** for this repository; replace it with **Manage Token…** |
| **GitHub couldn't find the repository at that address, or your account can't see it.** | A typo in the address, a renamed or deleted repository, or a private repository your account can't see | Open the address in your browser while signed in. Correct it with **Edit Repository…** |
| **Couldn't reach GitHub.** | No internet connection, a VPN or proxy problem, or GitHub is down | Check your connection; try again. [githubstatus.com](https://www.githubstatus.com) shows GitHub's status |
| **GitHub didn't respond in time, so the backup was stopped.** | A very slow connection, or a GitHub sign-in window waiting behind Fusion | Look for a sign-in window (check the taskbar); try again |
| **The connection to GitHub couldn't be verified as secure.** | A company network or antivirus program that inspects web traffic | Ask your IT team how Git should be set up on that network |
| **GitHub refused the backup because that branch is protected.** | The repository's main branch only accepts changes through pull requests | Set **Advanced → Backup branch** to a branch of its own, such as `fusion-backups` |
| **GitHub refused a file because it is too large (the limit is 100 MB).** | An export reached GitHub's limit | Untick that format, or choose a lower STL mesh refinement |
| **Another Git program is using this repository folder right now.** | GitHub Desktop, an editor or a terminal is working in the local folder, or a crashed program left a `.lock` file | Close the other program, or wait, then try again. If, after closing every Git program, it still happens, delete the `.lock` file named in the details |
| **The disk is full, so the backup couldn't be prepared.** | No space left for the temporary export or Git's data | Free some space, then try again |
| **Git isn't installed, or the add-in can't find it.** | Git missing, or installed somewhere unusual | Install Git from [git-scm.com](https://git-scm.com/downloads), restart Fusion, then **Check My Setup…** |
| **Git needs your name and email before it can save a backup.** | The name/email question was cancelled | Back up again and enter them |
| **Other changes kept arriving on GitHub while this backup was being sent.** | Someone else pushed to the same branch three times in a row during your backup | Wait a moment and back up again |
| **The backup didn't complete because Git reported an error.** | Anything else | The technical details say what Git ran into; [ask for help](#getting-help) with them |

**A cancelled backup** says whether GitHub had already received it (no need to
back up again), whether nothing was sent, or, if the connection broke at the
wrong moment, that it couldn't tell. In that last case, look at the repository
on GitHub before backing up again.

## Stored token messages

These protect your token; the backup is refused before anything is sent.

| Message (beginning) | Fix |
|---|---|
| *No stored token was found* | Store one with **Manage Token…**, or untick **Use stored token** |
| *The stored token was saved for <server>, but this repository's address is on <other server>* | Store a token for this server, or untick **Use stored token** |
| *This repository's own Git settings (.git/config) change how Git connects…* | The local folder sets a proxy or TLS option of its own. If you didn't set it, remove it with the command shown; if you need it, put it in your global Git settings instead |
| *This repository's Git settings would send the push to <address>, not to <saved address>* | The folder's Git settings (`remote.origin.pushurl`, `url.*.insteadOf`) point elsewhere. Check them, or correct the saved address with **Edit Repository…** |
| *The stored token contains a line break…* | Store the token again with **Manage Token…**, pasting only the token |

See [SECURITY.md](../SECURITY.md) for why.

## Export messages

| Message | Fix |
|---|---|
| *Nothing was pushed because these exports failed: …* | The list says which file and why (not created, empty, wrong type, over 100 MB). Try again; if one format keeps failing, untick it and report it |
| *None of the chosen file types can be exported from this design.* | Choose another file type |
| *No Fusion design is open.* | Open the design, then click the button |
| *This design uses … linked components…* (a question) | See [restore → linked components](RESTORE.md#designs-with-linked-components). **No** backs up nothing |
| *These exports are large… Push anyway?* | Files over 50 MB grow the repository quickly. **No** backs up nothing |
| *STL files have no units. This version of Fusion can't be told to write millimetres…* (a note) | Your Fusion version can't choose the STL unit; the files use the design's units. Check the scale when importing |

## Settings messages

Your settings are in `.fusion_git_repos.json` in your home folder.

| Message | What happened | Fix |
|---|---|---|
| *Your settings file couldn't be read (…). A copy was saved as …* | The file was damaged; the add-in kept a copy (`.corrupt-<date>`) and started with no saved repositories | Set your repositories up again (your backups on GitHub are unaffected), or repair the copy and put it back |
| *Your settings were saved by a newer version of the add-in…* | You went back to an older version | They're shown read-only. Update the add-in to change them, or see [going back](INSTALL.md#go-back-to-an-earlier-version) |
| *Some saved repositories have problems and are hidden until fixed* | A hand-edited entry is invalid | It's kept unchanged in the file; fix or remove it there |
| *The last settings save was interrupted; it has been completed.* | Fusion closed during a save | Nothing to do |

## Setting up a repository

| Message (beginning) | Fix |
|---|---|
| *The folder … is already connected to … Connect it to … instead?* | The local folder belongs to another repository. **No** keeps it; choose another folder |
| *… is already in the list with a different address or folder* | Choose another name, or select the saved entry |
| *The local folder for '…' isn't a Git repository folder* | The folder was moved or deleted. Choose it with **Edit Repository…**, or remove the entry and set it up again |
| A note that the folder is inside OneDrive, Dropbox, iCloud Drive or Google Drive | It works, but sync apps can lock or duplicate Git's files. A folder outside them is safer |

## Fusion seems busy, or the backup takes long

Only the export runs in Fusion. The rest runs in the background, and Fusion
stays usable: the progress window shows what's happening, and **Cancel** stops
it. Every network step stops by itself after 10 minutes, and a transfer that
stalls is cut off after a minute. Only one backup runs at a time; a second
click says one is already running.

If a GitHub sign-in window is waiting, it may be behind Fusion: check the
taskbar.

## After an update, the old version still runs

Restart Fusion. Versions from 0.6.0 on are designed to update without a
restart (not yet confirmed in Fusion itself), but updating *from* an older
version needs one. See
[Install → Update](INSTALL.md#update-to-a-new-version).

## Getting help

1. Run **Check My Setup…** and note its results.
2. Open the log: **Help & Privacy → Open Log File…**. Set **Log detail** to
   **DEBUG** and try again for more detail.
3. Follow [SUPPORT.md](../SUPPORT.md). Please remove tokens and anything private
   (repository names, design names) from what you paste. The log never contains
   tokens or passwords, but it does contain folder paths, repository addresses
   and design names.
