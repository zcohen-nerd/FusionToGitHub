"""Saved settings and repository profiles (~/.fusion_git_repos.json).

No Fusion dependencies, so everything here is tested outside Fusion.

Guarantees:

- **Atomic writes.** A save writes a temporary file next to the settings
  file, flushes it to disk, then renames it over the original. An
  interrupted save leaves either the old or the new file, never half of one.
- **Recovery.** If a save was interrupted after the temporary file was
  complete but before the rename, the next load uses that newer file.
- **Never silently discarded.** A file that can't be read is copied to
  ``<file>.corrupt-<timestamp>`` before anything else happens, and the load
  result says so. If that copy can't be made, saving is refused.
- **Versioned.** Files carry ``schemaVersion``. Files from versions before
  0.5.0 (no version) are migrated in memory and backed up once to
  ``<file>.v0-backup`` before they are first rewritten. A file from a *newer*
  version is opened read-only, so an older add-in can't damage it.
- **Profiles that fail validation are kept** in the file unchanged; they are
  reported, not deleted.

Removing a profile only removes its entry here. It never touches the local
folder, the GitHub repository or a stored token; callers ask about those
separately.
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .fusion_git_core import url_has_embedded_secret
from .portable_names import portable_name

SCHEMA_VERSION = 1
LEGACY_META_KEY = "__meta__"
KNOWN_FORMATS = ("f3d", "step", "stl", "iges", "sat")
# Settings older versions stored that no longer do anything (force push, a
# pre-filled branch override); dropped on migration.
OBSOLETE_PROFILE_KEYS = ("skipPullDefault", "lastBranchPreview")
RESERVED_NAMES = (LEGACY_META_KEY,)

IS_WINDOWS = os.name == "nt"


class SettingsError(RuntimeError):
    """Settings can't be read or written safely."""


@dataclass
class LoadReport:
    """What happened while loading, for the UI to explain to the user."""

    messages: List[str] = field(default_factory=list)
    backup_path: Optional[str] = None
    recovered_from_temp: bool = False
    migrated_from: Optional[int] = None
    invalid_profiles: Dict[str, List[str]] = field(default_factory=dict)
    read_only: bool = False


def _write_private(path: str, data: bytes) -> None:
    """Write *data* to a new file that is owner-only from the moment it exists (POSIX)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def validate_profile(profile: Any) -> List[str]:
    """Return the problems with one repository profile ([] when it is usable)."""
    if not isinstance(profile, dict):
        return ["is not an object"]
    problems = []
    for key in ("path", "url", "defaultMessage", "branchFormat", "exportSubfolder", "logLevel"):
        if key in profile and not isinstance(profile[key], str):
            problems.append(f"'{key}' is not text")
    if not profile.get("path"):
        problems.append("has no local folder ('path')")
    if isinstance(profile.get("url"), str) and url_has_embedded_secret(profile["url"]):
        problems.append("has a password or token in its GitHub address ('url')")
    formats = profile.get("exportFormats", [])
    if not isinstance(formats, list) or not all(isinstance(f, str) for f in formats):
        problems.append("'exportFormats' is not a list of names")
    if "formatSettings" in profile and not isinstance(profile["formatSettings"], dict):
        problems.append("'formatSettings' is not an object")
    for key in ("useStoredPat", "publicationNoticeAccepted"):
        if key in profile and not isinstance(profile[key], bool):
            problems.append(f"'{key}' is not true/false")
    identity = profile.get("gitIdentity")
    if identity is not None and not (
        isinstance(identity, dict)
        and isinstance(identity.get("name", ""), str)
        and isinstance(identity.get("email", ""), str)
    ):
        problems.append("'gitIdentity' is not {name, email}")
    designs = profile.get("designs")
    if designs is not None and not (
        isinstance(designs, dict) and all(isinstance(v, dict) and isinstance(v.get("folder"), str) for v in designs.values())
    ):
        problems.append("'designs' is not a map of design folders")
    return problems


def migrate(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert any supported older layout to the current schema (returns a new dict)."""
    if raw.get("schemaVersion") == SCHEMA_VERSION:
        data = copy.deepcopy(raw)
        # A hand-edited file can have the right version but the wrong shapes.
        if not isinstance(data.get("meta"), dict):
            data["meta"] = {}
        if not isinstance(data.get("repositories"), dict):
            data["repositories"] = {}
        return data
    # Version 0 (before 0.5.0): {"<repo name>": {...}, "__meta__": {...}}
    meta = raw.get(LEGACY_META_KEY, {})
    repositories = {}
    for name, profile in raw.items():
        if name == LEGACY_META_KEY:
            continue
        profile = copy.deepcopy(profile)
        if isinstance(profile, dict):
            for key in OBSOLETE_PROFILE_KEYS:
                profile.pop(key, None)
        repositories[name] = profile
    return {
        "schemaVersion": SCHEMA_VERSION,
        "meta": copy.deepcopy(meta) if isinstance(meta, dict) else {},
        "repositories": repositories,
    }


class SettingsStore:
    """Load, edit and atomically save the settings file."""

    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "meta": {}, "repositories": {}}
        self.report = LoadReport()
        self._needs_v0_backup = False

    # -- loading -----------------------------------------------------------

    @property
    def temp_path(self) -> str:
        return self.path + ".tmp"

    def _parse(self, path: str) -> Dict[str, Any]:
        with open(path, "rb") as fh:
            raw_bytes = fh.read()
        # utf-8-sig: Notepad and PowerShell can add a byte-order mark.
        text = raw_bytes.decode("utf-8-sig")
        if not text.strip():
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("the file does not contain a JSON object")
        return parsed

    def _preserve(self, path: str, suffix: str) -> Optional[str]:
        """Copy *path* to ``<settings file>.<suffix>-<timestamp>``; None if that failed.

        If an identical copy was already kept (the same damaged file seen on
        an earlier load), that copy is returned instead of making another.
        """
        content = b""
        try:
            with open(path, "rb") as fh:
                content = fh.read()
            directory = os.path.dirname(os.path.abspath(self.path)) or "."
            prefix = os.path.basename(self.path) + f".{suffix}-"
            for name in sorted(os.listdir(directory)):
                if name.startswith(prefix):
                    existing = os.path.join(directory, name)
                    with open(existing, "rb") as fh:
                        if fh.read() == content:
                            return existing
        except OSError:
            pass
        target = f"{self.path}.{suffix}-{_now_stamp()}"
        try:
            _write_private(target, content)
            self._make_private(target)
            return target
        except OSError:
            return None

    def load(self) -> LoadReport:
        """Read the settings file. Never raises for bad content; see the report."""
        self.report = LoadReport()
        raw: Optional[Dict[str, Any]] = None

        if os.path.exists(self.temp_path):
            # A save was interrupted. If the temporary file is complete, it
            # is newer than the main file: finish that save now.
            try:
                candidate = self._parse(self.temp_path)
                if candidate:
                    raw = candidate
                    os.replace(self.temp_path, self.path)
                    self.report.recovered_from_temp = True
                    self.report.messages.append(
                        "The last settings save was interrupted; it has been completed."
                    )
                else:
                    os.remove(self.temp_path)
            except (OSError, ValueError, UnicodeDecodeError):
                kept = self._preserve(self.temp_path, "incomplete")
                try:
                    os.remove(self.temp_path)
                except OSError:
                    pass
                if kept:
                    self.report.messages.append(f"An incomplete settings save was set aside as {kept}.")

        if raw is None and os.path.exists(self.path):
            try:
                raw = self._parse(self.path)
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                backup = self._preserve(self.path, "corrupt")
                self.report.backup_path = backup
                if backup:
                    self.report.messages.append(
                        f"Your settings file couldn't be read ({exc}). A copy was saved as\n{backup}\n"
                        "The add-in starts with no saved repositories; your local folders and "
                        "GitHub repositories are not affected."
                    )
                else:
                    self.report.read_only = True
                    self.report.messages.append(
                        f"Your settings file couldn't be read ({exc}), and a backup copy couldn't be "
                        "made, so the add-in won't overwrite it. Fix or move the file:\n" + self.path
                    )
                raw = {}

        raw = raw or {}
        version = raw.get("schemaVersion", 0)
        if not isinstance(version, int):
            version = 0
        if version > SCHEMA_VERSION:
            # Written by a newer add-in: show it, but never write it back.
            self.report.read_only = True
            self.report.messages.append(
                "Your settings were saved by a newer version of the add-in. They are shown "
                "read-only so this version can't damage them; update the add-in to change them."
            )
            self.data = copy.deepcopy(raw)
            if not isinstance(self.data.get("meta"), dict):
                self.data["meta"] = {}
            if not isinstance(self.data.get("repositories"), dict):
                self.data["repositories"] = {}
        else:
            if version < SCHEMA_VERSION and raw:
                self.report.migrated_from = version
                self._needs_v0_backup = True
            self.data = migrate(raw)

        for name, profile in self.data.get("repositories", {}).items():
            problems = validate_profile(profile)
            if problems:
                self.report.invalid_profiles[name] = problems
        if self.report.invalid_profiles:
            names = ", ".join(sorted(self.report.invalid_profiles))
            self.report.messages.append(
                f"Some saved repositories have problems and are hidden until fixed: {names}. "
                "They are kept in the settings file unchanged."
            )
        self._make_private(self.path)
        return self.report

    # -- saving ------------------------------------------------------------

    @staticmethod
    def _make_private(path: str) -> None:
        if IS_WINDOWS or not os.path.exists(path):
            return
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def save(self) -> None:
        """Atomically write the settings. Raises SettingsError if that isn't safe."""
        if self.report.read_only:
            raise SettingsError("Settings are read-only for this session; nothing was saved.")
        if self._needs_v0_backup and os.path.exists(self.path):
            # Keep the pre-0.5.0 file once, exactly as it was, before the
            # first save in the new format.
            backup = self.path + ".v0-backup"
            if not os.path.exists(backup):
                try:
                    with open(self.path, "rb") as fh:
                        _write_private(backup, fh.read())
                except OSError as exc:
                    raise SettingsError(
                        f"Couldn't back up the old settings file before converting it: {exc}"
                    ) from exc
                self._make_private(backup)
            self._needs_v0_backup = False
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        payload = json.dumps(self.data, indent=4, ensure_ascii=False).encode("utf-8")
        _write_private(self.temp_path, payload)
        self._make_private(self.temp_path)
        os.replace(self.temp_path, self.path)
        if not IS_WINDOWS:
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass

    # -- profiles ----------------------------------------------------------

    @property
    def meta(self) -> Dict[str, Any]:
        return self.data.setdefault("meta", {})

    @property
    def repositories(self) -> Dict[str, Any]:
        return self.data.setdefault("repositories", {})

    def profile_names(self) -> List[str]:
        """Usable profiles, sorted; invalid ones are left out (but kept in the file)."""
        return sorted(n for n in self.repositories if n not in self.report.invalid_profiles)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        profile = self.repositories.get(name)
        return profile if isinstance(profile, dict) else None

    @staticmethod
    def check_name(name: str) -> str:
        clean = (name or "").strip()
        if not clean:
            raise SettingsError("A repository name can't be empty.")
        if clean in RESERVED_NAMES or clean.startswith("__"):
            raise SettingsError(f"'{clean}' is reserved; choose another name.")
        return clean

    def add(self, name: str, profile: Dict[str, Any]) -> str:
        clean = self.check_name(name)
        if clean in self.report.invalid_profiles:
            raise SettingsError(
                f"'{clean}' is the name of a saved repository that is hidden because its settings "
                "have problems. Choose another name, or fix that entry in the settings file."
            )
        if clean in self.repositories:
            raise SettingsError(f"A repository named '{clean}' already exists.")
        problems = validate_profile(profile)
        if problems:
            raise SettingsError(f"Repository '{clean}' " + "; ".join(problems) + ".")
        self.repositories[clean] = copy.deepcopy(profile)
        return clean

    def update(self, name: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        profile = self.get(name)
        if profile is None:
            raise SettingsError(f"There is no saved repository named '{name}'.")
        candidate = copy.deepcopy(profile)
        candidate.update(copy.deepcopy(changes))
        problems = validate_profile(candidate)
        if problems:
            raise SettingsError(f"Repository '{name}' " + "; ".join(problems) + ".")
        self.repositories[name] = candidate
        self.report.invalid_profiles.pop(name, None)
        return candidate

    def rename(self, old: str, new: str) -> str:
        if old not in self.repositories:
            raise SettingsError(f"There is no saved repository named '{old}'.")
        clean = self.check_name(new)
        if clean == old:
            return clean
        if clean in self.repositories:
            raise SettingsError(f"A repository named '{clean}' already exists.")
        # Keep insertion order stable apart from the renamed entry.
        self.data["repositories"] = {
            (clean if key == old else key): value for key, value in self.repositories.items()
        }
        if self.meta.get("lastSelectedRepo") == old:
            self.meta["lastSelectedRepo"] = clean
        return clean

    def remove(self, name: str) -> Dict[str, Any]:
        """Forget a profile. Returns it, so the caller can offer related clean-up."""
        if name not in self.repositories:
            raise SettingsError(f"There is no saved repository named '{name}'.")
        removed = self.repositories.pop(name)
        self.report.invalid_profiles.pop(name, None)
        if self.meta.get("lastSelectedRepo") == name:
            self.meta.pop("lastSelectedRepo", None)
        return removed


# -- per-design folders (decision Q11) ---------------------------------------

_FOLDER_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_folder_name(name: str) -> str:
    """A design name that works as a folder on Windows, macOS and GitHub (see portable_names)."""
    return portable_name(name, fallback="Design")


def design_folder(profile: Dict[str, Any], design_id: str, design_name: str) -> str:
    """The folder for a design's exports and HISTORY.md, stable across renames.

    The first time a design (identified by *design_id*) is pushed with this
    profile it gets a folder named after it; a different design that already
    uses that name gets a numbered folder ("Bracket (2)") instead of sharing
    it. Renaming a design in Fusion keeps its folder. The mapping is stored in
    the profile (``designs``), so it updates *profile* in place.
    """
    designs = profile.setdefault("designs", {})
    entry = designs.get(design_id)
    if isinstance(entry, dict) and entry.get("folder"):
        entry["name"] = design_name
        return entry["folder"]
    if not design_id.startswith("name:"):
        # The same design pushed before it was saved to the cloud had a
        # name-based id; it now has a stable one. Keep its folder and history.
        for provisional in (f"name:{design_name}", f"name:{safe_folder_name(design_name)}"):
            earlier = designs.get(provisional)
            if isinstance(earlier, dict) and earlier.get("folder"):
                designs[design_id] = designs.pop(provisional)
                designs[design_id]["name"] = design_name
                return designs[design_id]["folder"]
    base = safe_folder_name(design_name)
    taken = {v.get("folder", "").lower() for v in designs.values() if isinstance(v, dict)}
    folder, n = base, 2
    while folder.lower() in taken:
        folder = f"{base} ({n})"
        n += 1
    designs[design_id] = {"folder": folder, "name": design_name}
    return folder


__all__ = [
    "SCHEMA_VERSION",
    "KNOWN_FORMATS",
    "LoadReport",
    "SettingsError",
    "SettingsStore",
    "design_folder",
    "migrate",
    "safe_folder_name",
    "validate_profile",
]
