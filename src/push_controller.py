"""Push workflow and repository-profile management, without Fusion.

The Fusion dialog collects input and exports the design; everything after
that is decided here, so it can be tested outside Fusion.

A push has two phases, split so that a later version can run the second one
on a background thread (decision Q6):

1. ``plan()`` runs on Fusion's main thread. It may ask the user questions
   (identity, the one-time publication notice) and reads settings and the
   stored token. It returns a ``PushPlan``: plain data, no Fusion objects.
2. ``execute(plan)`` runs git only. It never touches Fusion; its only
   interaction is through the ``GitUI`` it is given.

Profile edits never delete local folders, GitHub repositories, Git history
or stored tokens unless the caller explicitly asks for that.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import fusion_git_core as git_core
from credentials import CredentialError, CredentialStore
from dialog_helpers import expand_export_subfolder, normalize_export_subfolder, publication_notice
from settings_store import SettingsError, SettingsStore, design_folder

HISTORY_FILE_NAME = "HISTORY.md"
LEGACY_HISTORY_FILE = "CHANGELOG.md"
DEFAULT_COMMIT_TEMPLATE = "Design update: {filename}"
DEFAULT_BRANCH_FORMAT = "fusion-export/{filename}-{timestamp}"

# ask_identity() -> (name, email, use_for_all_repositories) or None if cancelled
IdentityPrompt = Callable[[], Optional[Tuple[str, str, bool]]]


class PushCancelled(Exception):
    """The user declined a question; nothing was pushed."""


class PushRefused(Exception):
    """The push can't go ahead; the message explains why, for the user."""


@dataclass
class PushRequest:
    profile_name: str
    design_name: str
    design_id: str
    commit_message: str = ""
    branch_override: str = ""


@dataclass
class PushPlan:
    """Everything ``execute`` needs. Plain data: safe to hand to another thread."""

    profile_name: str
    repo_path: str
    exports: List[Tuple[str, str]]
    message_template: str
    design_name: str
    mode: str = git_core.MODE_SNAPSHOT
    branch_format: str = DEFAULT_BRANCH_FORMAT
    branch_override: Optional[str] = None
    history_file: Optional[str] = None
    history_title: Optional[str] = None
    legacy_history_file: Optional[str] = LEGACY_HISTORY_FILE
    identity: Optional[Dict[str, str]] = None
    pat_credentials: Optional[Dict[str, str]] = field(default=None, repr=False)


def design_destination(profile: Dict[str, Any], design_id: str, design_name: str) -> Tuple[str, str]:
    """Return (folder for the design's exports, path of its HISTORY.md) in the repository.

    Each design gets its own folder, named once from the design and then kept
    even if the design is renamed (decision Q11). An Export Subfolder setting
    is the parent folder; one that already contains ``{filename}`` is used as
    the design's folder itself.
    """
    template = normalize_export_subfolder(profile.get("exportSubfolder", ""))
    folder_name = design_folder(profile, design_id, design_name)
    if "{filename}" in template:
        folder = expand_export_subfolder(template, folder_name)
    else:
        folder = "/".join(p for p in (expand_export_subfolder(template, folder_name), folder_name) if p)
    return folder, f"{folder}/{HISTORY_FILE_NAME}"


def _host(url: str) -> str:
    try:
        if url.startswith("git@") and ":" in url:
            return url[len("git@"):].split(":", 1)[0].lower()
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class PushController:
    def __init__(
        self,
        store: SettingsStore,
        credential_store: CredentialStore,
        logger: Optional[logging.Logger] = None,
        git=git_core,
    ):
        self.store = store
        self.credentials = credential_store
        self.logger = logger
        self.git = git

    # -- profiles ----------------------------------------------------------

    def profile(self, name: str) -> Dict[str, Any]:
        profile = self.store.get(name)
        if profile is None:
            raise PushRefused(f"The saved repository '{name}' no longer exists.")
        return profile

    def remove_profile(self, name: str, delete_token: bool = False) -> Dict[str, Any]:
        """Forget a saved repository; optionally delete its stored token.

        The local folder, the GitHub repository and its history are never
        touched. Returns the removed profile.
        """
        removed = self.store.remove(name)
        if delete_token:
            self.credentials.delete(name)
        self.store.save()
        return removed

    def edit_profile(
        self,
        name: str,
        new_name: Optional[str] = None,
        url: Optional[str] = None,
        path: Optional[str] = None,
        update_origin: Optional[Callable[[str, str, str], bool]] = None,
    ) -> Tuple[str, List[str]]:
        """Change a saved repository's name, address or local folder.

        Returns (final name, notes for the user). A new address is only
        written to the local repository's ``origin`` if *update_origin*
        (repo_path, old_url, new_url) agrees. If the address moves to a
        different server, "Use Stored Token" is turned off, so a token is
        never sent to a host it wasn't stored for.
        """
        notes: List[str] = []
        profile = self.profile(name)
        changes: Dict[str, Any] = {}
        if path is not None and path != profile.get("path"):
            expanded = os.path.expanduser(path)
            if not os.path.isdir(os.path.join(expanded, ".git")):
                raise SettingsError(f"'{path}' is not a Git repository folder.")
            changes["path"] = path
        if url is not None and url != profile.get("url", ""):
            if git_core.url_has_embedded_secret(url):
                raise SettingsError("The address contains a password or token; use the plain address.")
            old_url = profile.get("url", "")
            repo_path = os.path.expanduser(changes.get("path", profile.get("path", "")))
            if update_origin is not None and update_origin(repo_path, old_url, url):
                proc = self.git.git_run(repo_path, "remote", "set-url", "origin", url, check=False)
                if proc.returncode != 0:
                    raise SettingsError(f"Couldn't update the folder's GitHub address: {proc.stderr.strip()}")
                notes.append("The local folder now points to the new address.")
            else:
                notes.append("The local folder still points to the old address.")
            if profile.get("useStoredPat") and _host(old_url) != _host(url):
                changes["useStoredPat"] = False
                notes.append(
                    "'Use Stored Token' was turned off because the repository moved to another "
                    "server. Turn it on again once the stored token is right for the new one."
                )
            changes["url"] = url
            changes["publicationNoticeAccepted"] = False  # a new destination: say it again
        if changes:
            self.store.update(name, changes)
        final = name
        if new_name is not None and new_name.strip() != name:
            final = self.store.rename(name, new_name)
            try:
                self.credentials.rename(name, final)
            except CredentialError as exc:
                notes.append(f"The stored token couldn't be moved to the new name: {exc}")
        self.store.save()
        return final, notes

    # -- push: main-thread phase -------------------------------------------

    def needs_publication_notice(self, profile: Dict[str, Any]) -> bool:
        return not profile.get("publicationNoticeAccepted")

    def publication_notice_text(self, profile: Dict[str, Any], repo_path: str) -> str:
        url = profile.get("url") or ""
        if not url:
            proc = self.git.git_run(repo_path, "remote", "get-url", "origin", check=False)
            url = (proc.stdout or "").strip()
        return publication_notice(git_core.redact_secrets(url))

    def resolve_identity(
        self, name: str, profile: Dict[str, Any], repo_path: str, ask: Optional[IdentityPrompt]
    ) -> Optional[Dict[str, str]]:
        """The name and email to commit with (decision Q14).

        Order: the profile's own identity; otherwise whatever Git already has
        configured (returns None, so git uses it); otherwise ask. An answer
        is saved in the profile, not in the repository's .git/config; it goes
        into the global Git config only if the user explicitly chooses
        "all repositories".
        """
        saved = profile.get("gitIdentity")
        if isinstance(saved, dict) and saved.get("name") and saved.get("email"):
            return {"name": saved["name"], "email": saved["email"]}

        def configured(key: str) -> str:
            proc = self.git.git_run(repo_path, "config", "--get", key, check=False)
            return (proc.stdout or "").strip()

        if configured("user.name") and configured("user.email"):
            return None
        if ask is None:
            raise PushRefused("Git needs your name and email to sign commits.")
        answer = ask()
        if not answer:
            raise PushCancelled()
        user_name, email, use_everywhere = (answer[0] or "").strip(), (answer[1] or "").strip(), bool(answer[2])
        if not user_name or "@" not in email:
            raise PushRefused("A name and a valid email address are both needed.")
        identity = {"name": user_name, "email": email}
        if use_everywhere:
            for key, value in (("user.name", user_name), ("user.email", email)):
                self.git.git_run(repo_path, "config", "--global", key, value)
        self.store.update(name, {"gitIdentity": identity})
        return identity

    def plan(
        self,
        request: PushRequest,
        exported_files: Sequence[str],
        *,
        confirm: Callable[[str], bool],
        ask_identity: Optional[IdentityPrompt] = None,
    ) -> PushPlan:
        """Decide everything about a push. Raises PushCancelled or PushRefused."""
        profile = self.profile(request.profile_name)
        repo_path = os.path.expanduser(profile.get("path", "")).replace("/", os.sep)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            raise PushRefused(f"The folder '{repo_path}' for '{request.profile_name}' is not a Git repository.")
        if not exported_files:
            raise PushRefused("No files were exported, so there is nothing to push.")

        if self.needs_publication_notice(profile):
            if not confirm(self.publication_notice_text(profile, repo_path)):
                raise PushCancelled()
            self.store.update(request.profile_name, {"publicationNoticeAccepted": True})

        identity = self.resolve_identity(request.profile_name, profile, repo_path, ask_identity)

        pat = None
        if profile.get("useStoredPat"):
            if not self.credentials.available:
                raise PushRefused("Stored tokens aren't supported on this computer; untick 'Use Stored Token'.")
            pat = self.credentials.get(request.profile_name)
            if not pat:
                raise PushRefused("No stored token was found. Use 'Manage Token…' to add one first.")

        profile = self.profile(request.profile_name)  # re-read: updates above changed it
        folder, history_file = design_destination(profile, request.design_id, request.design_name)
        exports = [(path, f"{folder}/{os.path.basename(path)}") for path in exported_files]
        self.store.update(request.profile_name, {"designs": profile.get("designs", {})})
        self.store.save()

        override = (request.branch_override or "").strip()
        return PushPlan(
            profile_name=request.profile_name,
            repo_path=repo_path,
            exports=exports,
            message_template=request.commit_message.strip()
            or profile.get("defaultMessage")
            or DEFAULT_COMMIT_TEMPLATE,
            design_name=request.design_name,
            mode=profile.get("historyMode", git_core.MODE_SNAPSHOT),
            branch_format=profile.get("branchFormat") or DEFAULT_BRANCH_FORMAT,
            branch_override=git_core.sanitize_branch_name(override) if override else None,
            history_file=history_file,
            history_title=f"History: {request.design_name}",
            identity=identity,
            pat_credentials=pat,
        )

    # -- push: git phase (no Fusion; background-safe) -----------------------

    def execute(
        self, plan: PushPlan, ui: git_core.GitUI, on_step: Optional[Callable[[str], None]] = None
    ) -> Optional[Dict[str, Any]]:
        """Run the push. Returns push_export's result: a dict, {"cancelled": True}, or None."""
        return self.git.push_export(
            plan.repo_path,
            plan.exports,
            plan.message_template,
            plan.design_name,
            ui,
            mode=plan.mode,
            branch_format_str=plan.branch_format,
            branch_override=plan.branch_override,
            history_file=plan.history_file,
            history_title=plan.history_title,
            legacy_history_file=plan.legacy_history_file,
            identity=plan.identity,
            pat_credentials=plan.pat_credentials,
            logger=self.logger,
            on_step=on_step,
        )


__all__ = [
    "HISTORY_FILE_NAME",
    "LEGACY_HISTORY_FILE",
    "PushCancelled",
    "PushController",
    "PushPlan",
    "PushRefused",
    "PushRequest",
    "design_destination",
]
