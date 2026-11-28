"""Push workflow and repository-profile management, without Fusion.

The Fusion dialog collects input and exports the design; everything after
that is decided here, so it can be tested outside Fusion.

A push has two phases, split so that a later version can run the second one
on a background thread (decision Q6):

1. ``plan()`` runs on Fusion's main thread. It may ask the user questions
   (identity, the one-time publication notice) and reads settings and the
   stored token. It returns a ``PushPlan``: plain data, no Fusion objects.
2. ``execute(plan)`` runs git only and makes no Fusion API calls itself. Its
   interaction goes through the ``GitUI`` it is given, which today shows
   Fusion message boxes; a background thread must hand those calls back to
   the main thread (S4).

Profile edits never delete local folders, GitHub repositories, Git history
or stored tokens unless the caller explicitly asks for that, and they are
all-or-nothing: a failed edit or removal leaves settings and tokens as they
were.
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from . import fusion_git_core as git_core
from .credentials import CredentialError, CredentialStore
from .dialog_helpers import expand_export_subfolder, normalize_export_subfolder, publication_notice
from .settings_store import SettingsError, SettingsStore, design_folder, history_mode

HISTORY_FILE_NAME = "HISTORY.md"
LEGACY_HISTORY_FILE = "CHANGELOG.md"
# "{message}" is what the user typed in "What changed?". Templates saved
# before 0.7.0 have no "{message}"; for them the typed text is the whole
# commit message, as before.
DEFAULT_COMMIT_TEMPLATE = "{filename}: {message}"
DEFAULT_BRANCH_FORMAT = "fusion-export/{filename}-{timestamp}"
# Where new profiles put each design's folder (decision 1: designs/<name>/).
NEW_PROFILE_SUBFOLDER = "designs"
FALLBACK_MESSAGE = "Design update"


def new_profile_settings() -> Dict[str, Any]:
    """Settings a repository set up with this version starts with (audit UX-01).

    One running history on the repository's default branch, each design in
    ``designs/<name>/``. Profiles saved by earlier versions don't have
    ``historyMode`` and keep their snapshot branches (settings_store.history_mode).
    """
    return {
        "historyMode": git_core.MODE_SINGLE,
        "targetBranch": "",
        "exportSubfolder": NEW_PROFILE_SUBFOLDER,
        "defaultMessage": DEFAULT_COMMIT_TEMPLATE,
        "branchFormat": DEFAULT_BRANCH_FORMAT,
    }


def compose_commit_message(template: str, typed: str) -> str:
    """The commit message template with what the user typed ("What changed?") filled in."""
    typed = git_core.single_line(typed)
    template = template or DEFAULT_COMMIT_TEMPLATE
    if "{message}" in template:
        return template.replace("{message}", typed or FALLBACK_MESSAGE)
    return typed or template

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
    # Recorded in the design's HISTORY.md entry (for example, that the design
    # has linked components and the backup may not be self-contained).
    history_notes: List[str] = field(default_factory=list)
    # The Fusion version that was backed up, as text ("v12", "v12 with
    # unsaved changes", "not saved yet"); recorded in HISTORY.md.
    fusion_version: str = ""


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
    notes: List[str] = field(default_factory=list)
    history_notes: List[str] = field(default_factory=list)
    # Set once the "these exports are large" question was answered Yes (on
    # Fusion's main thread), so the background push doesn't ask it again.
    large_files_confirmed: bool = False
    target_branch: Optional[str] = None
    # The design and its folder, so the push can check the folder against
    # GitHub and move it if another design owns it (risk R-24).
    design_id: str = ""
    design_folder: str = ""
    export_template: str = ""
    source_files: List[str] = field(default_factory=list)
    fusion_version: str = ""


def design_destination(profile: Dict[str, Any], design_id: str, design_name: str) -> Tuple[str, str]:
    """Return (folder for the design's exports, path of its HISTORY.md) in the repository.

    Each design gets its own folder, named once from the design and then kept
    even if the design is renamed (decision Q11). An Export Subfolder setting
    is the parent folder; one that already contains ``{filename}`` is used as
    the design's folder itself.

    ``HISTORY.md`` always lives in a folder that is the same on every push: a
    ``{timestamp}`` part of the template (a new folder per push) applies to
    the exports only, so the history keeps accumulating in one file.
    """
    template = normalize_export_subfolder(profile.get("exportSubfolder", ""))
    return destination_for(template, design_folder(profile, design_id, design_name))


def destination_for(template: str, folder_name: str) -> Tuple[str, str]:
    """(export folder, HISTORY.md path) for a design whose folder is *folder_name*."""

    def place(tmpl: str) -> str:
        if "{filename}" in tmpl:
            return expand_export_subfolder(tmpl, folder_name)
        return "/".join(p for p in (expand_export_subfolder(tmpl, folder_name), folder_name) if p)

    export_folder = place(template)
    segments = template.split("/") if template else []
    stable = []
    for segment in segments:
        if "{timestamp}" in segment:
            break
        stable.append(segment)
    stable_template = "/".join(stable)
    if "{filename}" in template and "{filename}" not in stable_template:
        # The design's own folder comes after the per-push part; keep the
        # history next to the stable parent, in a folder named for the design.
        history_folder = "/".join(p for p in (expand_export_subfolder(stable_template, folder_name), folder_name) if p)
    else:
        history_folder = place(stable_template)
    return export_folder, f"{history_folder}/{HISTORY_FILE_NAME}"


def server_of(url: str) -> str:
    """The server part of a Git address, lower case, with any port ("" if unknown)."""
    url = (url or "").strip()
    try:
        if "://" not in url and "@" in url and ":" in url.split("@", 1)[1]:
            return url.split("@", 1)[1].split(":", 1)[0].lower()  # git@host:owner/repo
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if host and parsed.port:
            host += f":{parsed.port}"
        return host
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

    # -- helpers -----------------------------------------------------------

    def profile(self, name: str) -> Dict[str, Any]:
        profile = self.store.get(name)
        if profile is None:
            raise PushRefused(f"The saved repository '{name}' no longer exists.")
        return profile

    def _require_writable(self) -> None:
        if self.store.report.read_only:
            raise SettingsError("Settings are read-only for this session, so nothing can be changed.")

    def origin_url(self, repo_path: str) -> str:
        proc = self.git.git_run(repo_path, "remote", "get-url", "--push", "origin", check=False)
        return (proc.stdout or "").strip() if proc.returncode == 0 else ""

    def _transaction(self, change: Callable[[], Any]) -> Any:
        """Apply *change* to the settings and save; on any failure restore them exactly."""
        self._require_writable()
        snapshot = copy.deepcopy(self.store.data)
        invalid = copy.deepcopy(self.store.report.invalid_profiles)
        try:
            result = change()
            self.store.save()
            return result
        except BaseException:
            self.store.data = snapshot
            self.store.report.invalid_profiles = invalid
            raise

    # -- stored token ------------------------------------------------------

    def store_token(self, name: str, username: str, token: str) -> str:
        """Save a token for a profile, bound to the server its repository is on.

        Returns that server. The binding is stored with the token, so it moves
        with the token on rename and survives removing the profile.
        """
        profile = self.profile(name)
        repo_path = os.path.expanduser(profile.get("path", ""))
        # The server the push will really use; the saved address only if the
        # folder's remote has none (the push-time check uses the remote).
        host = server_of(self.origin_url(repo_path)) or server_of(profile.get("url", ""))
        if not host:
            raise CredentialError("This repository has no GitHub address, so a token can't be stored for it.")
        self.credentials.set(name, username, token, host)
        return host

    # -- profiles ----------------------------------------------------------

    def remove_profile(self, name: str, delete_token: bool = False) -> Tuple[Dict[str, Any], List[str]]:
        """Forget a saved repository; optionally delete its stored token.

        The local folder, the GitHub repository and its history are never
        touched. The settings are saved first; the token is only deleted once
        that has succeeded. Returns (removed profile, notes for the user).
        """
        removed = self._transaction(lambda: self.store.remove(name))
        notes: List[str] = []
        if delete_token:
            try:
                self.credentials.delete(name)
            except CredentialError as exc:
                notes.append(f"The stored token couldn't be deleted ({exc}); remove it in Windows Credential Manager.")
        return removed, notes

    def edit_profile(
        self,
        name: str,
        new_name: Optional[str] = None,
        url: Optional[str] = None,
        path: Optional[str] = None,
        update_origin: Optional[Callable[[str, str, str], bool]] = None,
    ) -> Tuple[str, List[str]]:
        """Change a saved repository's name, address or local folder, all or nothing.

        Everything is checked before anything changes. The local repository's
        ``origin`` is rewritten only if *update_origin* (repo_path, old_url,
        new_url) agrees, and only after the settings were saved. Moving to a
        different folder or server turns off "Use Stored Token", so a token is
        never sent somewhere it wasn't stored for. Returns (final name, notes).
        """
        self._require_writable()
        profile = self.profile(name)
        notes: List[str] = []
        changes: Dict[str, Any] = {}

        final = name
        if new_name is not None and new_name.strip() != name:
            final = self.store.check_name(new_name)
            if final in self.store.repositories:
                raise SettingsError(f"A repository named '{final}' already exists.")

        if path is not None and path != profile.get("path"):
            if not os.path.isdir(os.path.join(os.path.expanduser(path), ".git")):
                raise SettingsError(f"'{path}' is not a Git repository folder.")
            changes["path"] = path
            if profile.get("useStoredPat"):
                changes["useStoredPat"] = False
                notes.append(
                    "'Use Stored Token' was turned off because the repository now uses a different "
                    "folder. Turn it on again once you've checked the token is right for it."
                )

        old_url = profile.get("url", "")
        repo_path = os.path.expanduser(changes.get("path", profile.get("path", "")))
        repoint = False
        if url is not None and url != old_url:
            if git_core.url_has_embedded_secret(url):
                raise SettingsError("The address contains a password or token; use the plain address.")
            repoint = bool(update_origin and update_origin(repo_path, old_url, url))
            if profile.get("useStoredPat") and server_of(old_url) != server_of(url):
                changes["useStoredPat"] = False
                notes.append(
                    "'Use Stored Token' was turned off because the repository moved to another "
                    "server. Turn it on again once the stored token is right for the new one."
                )
            changes["url"] = url
            changes["publicationNoticeAccepted"] = False  # a new destination: say it again

        def apply() -> str:
            if changes:
                self.store.update(name, changes)
            if final != name:
                self.store.rename(name, final)
            return final

        self._transaction(apply)

        # The settings are saved; now the parts outside them.
        if final != name:
            try:
                self.credentials.rename(name, final)
            except CredentialError as exc:
                notes.append(f"The stored token couldn't be moved to the new name: {exc}")
        if "url" in changes:
            if repoint:
                proc = self.git.git_run(repo_path, "remote", "set-url", "origin", url, check=False)
                if proc.returncode == 0:
                    notes.append("The local folder now points to the new address.")
                else:
                    notes.append(f"The local folder's address couldn't be updated: {(proc.stderr or '').strip()}")
            else:
                notes.append("The local folder still points to the old address.")
        return final, notes

    # -- push: main-thread phase -------------------------------------------

    def needs_publication_notice(self, profile: Dict[str, Any]) -> bool:
        return not profile.get("publicationNoticeAccepted")

    def publication_notice_text(self, profile: Dict[str, Any], repo_path: str) -> str:
        url = profile.get("url") or self.origin_url(repo_path)
        return publication_notice(git_core.redact_secrets(url))

    def resolve_identity(
        self, name: str, profile: Dict[str, Any], repo_path: str, ask: Optional[IdentityPrompt],
        notes: Optional[List[str]] = None,
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
        self.store.update(name, {"gitIdentity": identity})
        if use_everywhere:
            try:
                for key, value in (("user.name", user_name), ("user.email", email)):
                    self.git.git_run(repo_path, "config", "--global", key, value)
            except git_core.GitError as exc:
                message = (
                    "Your name and email were saved for this repository, but couldn't be saved "
                    f"for all repositories: {exc}"
                )
                if notes is not None:
                    notes.append(message)
                if self.logger:
                    self.logger.warning(message)
        return identity

    def _token_for(self, name: str, repo_path: str) -> Dict[str, str]:
        """The stored token, after checking it was stored for this repository's server."""
        if not self.credentials.available:
            raise PushRefused("Stored tokens aren't supported on this computer; untick 'Use Stored Token'.")
        try:
            pat = self.credentials.get(name)
        except CredentialError as exc:
            raise PushRefused(f"The stored token couldn't be read: {exc}") from exc
        if not pat:
            raise PushRefused("No stored token was found. Use 'Manage Token…' to add one first.")
        server = server_of(self.origin_url(repo_path))
        bound = (pat.get("host") or "").lower()
        if not bound:
            # Saved before 0.5.0, without its server: bind it to this one now.
            try:
                self.credentials.set(name, pat.get("username", ""), pat["token"], server)
            except CredentialError as exc:
                if self.logger:
                    self.logger.warning("Couldn't record the stored token's server: %s", exc)
        elif bound != server:
            raise PushRefused(
                f"The stored token was saved for {bound}, but this repository's address is on "
                f"{server or 'an unknown server'}, so the token was not used. Untick 'Use Stored "
                "Token', or store a token for this server with 'Manage Token…'."
            )
        risky = git_core.risky_local_network_config(repo_path)
        if risky:
            raise PushRefused(git_core.risky_config_message(risky))
        elsewhere = git_core.token_destination_problem(repo_path, self.profile(name).get("url", ""))
        if elsewhere:
            raise PushRefused(elsewhere)
        return {"username": pat.get("username", ""), "token": pat["token"]}

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
        notes: List[str] = []
        try:
            if self.needs_publication_notice(profile):
                if not confirm(self.publication_notice_text(profile, repo_path)):
                    raise PushCancelled()
                self.store.update(request.profile_name, {"publicationNoticeAccepted": True})

            identity = self.resolve_identity(request.profile_name, profile, repo_path, ask_identity, notes)
            pat = self._token_for(request.profile_name, repo_path) if profile.get("useStoredPat") else None

            profile = self.profile(request.profile_name)  # re-read: updates above changed it
            folder, history_file = design_destination(profile, request.design_id, request.design_name)
            folder_name = profile["designs"][request.design_id]["folder"]
            exports = [(path, f"{folder}/{os.path.basename(path)}") for path in exported_files]
            self.store.update(request.profile_name, {"designs": profile.get("designs", {})})
            self.store.save()
        except (SettingsError, OSError, git_core.GitError, ValueError) as exc:
            raise PushRefused(f"The push couldn't be prepared: {git_core.redact_secrets(str(exc))}") from exc

        override = (request.branch_override or "").strip()
        return PushPlan(
            profile_name=request.profile_name,
            repo_path=repo_path,
            exports=exports,
            message_template=compose_commit_message(profile.get("defaultMessage", ""), request.commit_message),
            design_name=request.design_name,
            mode=history_mode(profile),
            branch_format=profile.get("branchFormat") or DEFAULT_BRANCH_FORMAT,
            branch_override=(git_core.sanitize_branch_name(override)
                             if override and history_mode(profile) == git_core.MODE_SNAPSHOT else None),
            history_file=history_file,
            history_title=f"History: {request.design_name}",
            identity=identity,
            pat_credentials=pat,
            notes=notes,
            history_notes=list(request.history_notes),
            target_branch=(profile.get("targetBranch") or "").strip() or None,
            design_id=request.design_id,
            design_folder=folder_name,
            export_template=normalize_export_subfolder(profile.get("exportSubfolder", "")),
            source_files=list(exported_files),
            fusion_version=request.fusion_version,
        )

    # -- push: git phase ----------------------------------------------------

    def execute(
        self,
        plan: PushPlan,
        ui: git_core.GitUI,
        on_step: Optional[Callable[[str], None]] = None,
        cancel=None,
    ) -> Optional[Dict[str, Any]]:
        """Run the push. Returns push_export's result: a dict, {"cancelled": True, ...}, or None.

        Makes no Fusion calls itself; *ui* and *on_step* are the only
        callbacks. Setting *cancel* (a threading.Event) stops the running git
        command; the result then says whether the export reached GitHub.
        """
        def relocate(folder_name: str):
            folder, history = destination_for(plan.export_template, folder_name)
            return [(path, f"{folder}/{os.path.basename(path)}") for path in plan.source_files], history

        can_relocate = bool(plan.design_id and plan.design_folder and plan.source_files and plan.history_file)
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
            history_notes=plan.history_notes,
            cancel=cancel,
            large_files_confirmed=plan.large_files_confirmed,
            target_branch=plan.target_branch,
            design_id=plan.design_id or None,
            design_folder=plan.design_folder or None,
            relocate=relocate if can_relocate else None,
            fusion_version=plan.fusion_version,
        )

    def record_result(self, plan: PushPlan, result: Optional[Dict[str, Any]]) -> Optional[str]:
        """After a push (main thread): remember a design folder the push moved to (risk R-24).

        Re-reads the settings file first, so a dialog opened meanwhile isn't
        overwritten with stale data. Returns the folder the design was moved
        away from (None if it stayed where it was).
        """
        result = result or {}
        folder = result.get("design_folder")
        if not folder or folder == plan.design_folder or not plan.design_id or result.get("cancelled"):
            return None
        fresh = SettingsStore(self.store.path)
        fresh.load()
        profile = fresh.get(plan.profile_name)
        if profile is not None and not fresh.report.read_only:
            designs = dict(profile.get("designs") or {})
            entry = dict(designs.get(plan.design_id) or {})
            entry.update(folder=folder, name=plan.design_name)
            designs[plan.design_id] = entry
            try:
                fresh.update(plan.profile_name, {"designs": designs})
                fresh.save()
                self.store.data = fresh.data
            except (SettingsError, OSError) as exc:
                # The markers on GitHub stay authoritative: the next push finds
                # the folder again even if this couldn't be saved.
                if self.logger:
                    self.logger.warning("Couldn't record the design's folder '%s': %s", folder, exc)
        return plan.design_folder


__all__ = [
    "HISTORY_FILE_NAME",
    "LEGACY_HISTORY_FILE",
    "PushCancelled",
    "PushController",
    "PushPlan",
    "PushRefused",
    "PushRequest",
    "compose_commit_message",
    "design_destination",
    "destination_for",
    "new_profile_settings",
    "server_of",
]
