"""Plain-language explanations for errors shown to the user (audit UX-04). No Fusion dependency.

Git's own messages ("fatal: unable to access ...: Could not resolve host")
and Python exceptions mean little to someone who has never used Git. Every
error that reaches a Fusion message box goes through :func:`explain`, which
puts a plain first line and a next step first and keeps the original text
underneath as "Technical details" (secrets already redacted by the caller),
so nothing needed for troubleshooting is lost.

A message the add-in wrote itself (it doesn't look like raw Git output and
matches no known pattern) is returned unchanged.

:func:`unexpected_error` replaces Python tracebacks: those go to the log
file only, never into a dialog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fusion_git_core import redact_secrets

DETAIL_MAX_LINES = 12
DETAIL_MAX_CHARS = 1200
LOG_HINT = "The log file has the full details (Help & Privacy → Open Log File)."


@dataclass(frozen=True)
class Explanation:
    key: str
    headline: str
    next_step: str


# Checked in order; the first match wins. Patterns are matched against the
# raw text, case-insensitively.
_CATALOG: List[Tuple[str, Explanation]] = [
    (r"exceeds GitHub's file size limit|GH001|Large files detected|this exceeds .* file size",
     Explanation("too_large", "GitHub refused a file because it is too large (the limit is 100 MB).",
                 "Untick that format, or choose a lower STL mesh refinement, and back up again.")),
    (r"protected branch|GH006|GH013|Changes must be made through a pull request",
     Explanation("protected_branch", "GitHub refused the backup because that branch is protected.",
                 "In Advanced, set Backup branch to a branch of its own (for example fusion-backups), "
                 "or ask the repository's owner to allow your pushes.")),
    (r"Repository not found|repository '.*' not found|does not appear to be a git repository|"
     r"remote: Not Found|returned error: 404",
     Explanation("not_found", "GitHub couldn't find the repository at that address, or your account can't see it.",
                 "Check the address (Edit Repository…), and that you're signed in with an account that has "
                 "access to the repository.")),
    (r"Authentication failed|Invalid username or password|could not read Username|could not read Password|"
     r"terminal prompts disabled|returned error: 401|returned error: 403|Permission to .* denied|"
     r"Write access to repository not granted|bad credentials|Permission denied \(publickey",
     Explanation("auth", "GitHub didn't accept your sign-in for this repository.",
                 "Back up again and sign in when the GitHub window opens. With a stored token, check it hasn't "
                 "expired and has Contents: Read and write access to this repository (Manage Token…).")),
    (r"SSL certificate problem|certificate verify failed|unable to get local issuer certificate|"
     r"server certificate verification failed|schannel: .*(certificate|revocation)",
     Explanation("tls", "The connection to GitHub couldn't be verified as secure.",
                 "This usually comes from a company network or antivirus that inspects web traffic. Ask your "
                 "IT team how Git should be set up on this network, then try again.")),
    (r"took longer than \d+ seconds|Operation timed out|Connection timed out|timed out after",
     Explanation("timeout", "GitHub didn't respond in time, so the backup was stopped.",
                 "Check your internet connection, and that no GitHub sign-in window is waiting behind Fusion, "
                 "then try again.")),
    (r"Could not resolve host|Couldn't resolve host|Failed to connect to|Connection refused|"
     r"Network is unreachable|No route to host|Connection reset|unable to access 'https?://|"
     r"Could not connect to server|proxy CONNECT aborted|early EOF|the remote end hung up unexpectedly",
     Explanation("network", "Couldn't reach GitHub.",
                 "Check your internet connection (and any company proxy or VPN), then try again. Nothing on "
                 "GitHub was changed.")),
    (r"index\.lock|\.lock': File exists|Unable to create '.*\.lock'|cannot lock ref",
     Explanation("lock", "Another Git program is using this repository folder right now.",
                 "Close other Git tools (GitHub Desktop, an editor, a terminal) or wait a moment, then try "
                 "again. If nothing else is running, a crashed program may have left the '.lock' file named "
                 "below; delete it and try again.")),
    (r"No space left on device|There is not enough space on the disk|disk quota exceeded",
     Explanation("disk_full", "The disk is full, so the backup couldn't be prepared.",
                 "Free some space on the drive that holds the repository folder and your temporary files, "
                 "then try again.")),
    (r"Git executable not found|git: command not found|No such file or directory: 'git'|"
     r"The system cannot find the file specified|WinError 2\]",
     Explanation("git_missing", "Git isn't installed, or the add-in can't find it.",
                 "Install Git from https://git-scm.com/downloads (on macOS, Homebrew or Xcode Command Line "
                 "Tools), restart Fusion, then use Check My Setup.")),
    (r"Please tell me who you are|unable to auto-detect email address|empty ident name",
     Explanation("identity", "Git needs your name and email before it can save a backup.",
                 "Back up again and enter them when the add-in asks.")),
    (r"kept receiving other changes on|\(\d+ attempts\)",
     Explanation("busy_branch", "Other changes kept arriving on GitHub while this backup was being sent.",
                 "Wait a moment and back up again. Nothing on GitHub was changed.")),
]
_COMPILED = [(re.compile(pattern, re.IGNORECASE), explanation) for pattern, explanation in _CATALOG]

# Lines that only raw Git output (or our "git <command> failed:" wrapper) has.
_RAW_GIT = re.compile(r"(^|\n)\s*(fatal|error|remote|hint|warning):|git [a-z-]+ .*failed:|^To https?://",
                      re.IGNORECASE)


def classify(text: str) -> Optional[Explanation]:
    """The catalog entry that matches *text*, or None."""
    for pattern, explanation in _COMPILED:
        if pattern.search(text or ""):
            return explanation
    return None


def _details(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").strip().splitlines() if line.strip()]
    if len(lines) > DETAIL_MAX_LINES:
        lines = lines[:DETAIL_MAX_LINES] + ["…"]
    detail = "\n".join(lines)
    if len(detail) > DETAIL_MAX_CHARS:
        detail = detail[:DETAIL_MAX_CHARS].rstrip() + "…"
    return detail


def explain(text: str, *, nothing_changed: bool = False) -> str:
    """*text* with a plain first line and a next step in front, when it is a Git error.

    *nothing_changed* adds "Nothing was pushed." when the caller knows that
    is true (the error came before anything was sent).
    """
    text = (text or "").strip()
    explanation = classify(text)
    if explanation is None and not _RAW_GIT.search(text):
        return text  # already a message written for people
    if explanation is None:
        headline = "The backup didn't complete because Git reported an error."
        next_step = "The details below say what Git ran into. " + LOG_HINT
    else:
        headline, next_step = explanation.headline, explanation.next_step
    parts = [headline]
    if nothing_changed and "Nothing" not in headline:
        parts[0] += " Nothing was pushed."
    parts += ["", next_step, "", "Technical details:", _details(text)]
    return "\n".join(parts)


def unexpected_error(what: str, exc: BaseException, *, nothing_pushed: bool = True) -> str:
    """A message for an unexpected exception, without a traceback.

    *what* says what was happening ("starting the backup"). The exception's
    type and first line are kept for support; the traceback goes to the log.
    """
    first_line = redact_secrets((str(exc).strip().splitlines() or [""])[0][:300])
    summary = type(exc).__name__ + (f": {first_line}" if first_line else "")
    lines = [f"Something went wrong while {what}."]
    if nothing_pushed:
        lines[0] += " Nothing was pushed."
    lines += ["", "Try again. If it happens again, " + LOG_HINT[0].lower() + LOG_HINT[1:],
              "", "Technical details:", summary]
    return "\n".join(lines)


def contains_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" in (text or "")


__all__ = ["Explanation", "LOG_HINT", "classify", "contains_traceback", "explain", "unexpected_error"]
