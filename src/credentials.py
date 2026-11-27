"""Where a repository's optional personal access token is kept.

On Windows the token lives in Windows Credential Manager, as a Generic
credential named ``FusionToGitHub::<repository name>`` (the same name every
earlier version used, so existing tokens keep working). Other platforms have
no stored-token support yet; their store reports ``available = False``.

``MemoryCredentialStore`` is a stand-in for tests. No Fusion dependencies.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Protocol

IS_WINDOWS = os.name == "nt"
TARGET_PREFIX = "FusionToGitHub::"


class CredentialError(RuntimeError):
    """The credential store refused an operation."""


class CredentialStore(Protocol):
    available: bool

    def get(self, name: str) -> Optional[Dict[str, str]]:
        """Return {"username", "token"} for profile *name*, or None."""

    def set(self, name: str, username: str, token: str) -> None: ...

    def delete(self, name: str) -> None:
        """Remove the token for *name*; no error if there is none."""

    def rename(self, old: str, new: str) -> None:
        """Move a stored token when its profile is renamed."""


def target_name(profile_name: str) -> str:
    return f"{TARGET_PREFIX}{profile_name}"


class MemoryCredentialStore:
    """In-memory store with the same behaviour, for tests."""

    available = True

    def __init__(self):
        self.items: Dict[str, Dict[str, str]] = {}

    def get(self, name):
        item = self.items.get(target_name(name))
        return dict(item) if item else None

    def set(self, name, username, token):
        if not token:
            raise CredentialError("The token is empty.")
        self.items[target_name(name)] = {"username": username or "", "token": token}

    def delete(self, name):
        self.items.pop(target_name(name), None)

    def rename(self, old, new):
        item = self.items.pop(target_name(old), None)
        if item is not None:
            self.items[target_name(new)] = item


class UnavailableCredentialStore:
    """Platforms without stored-token support (macOS, Linux)."""

    available = False

    def get(self, name):
        return None

    def set(self, name, username, token):
        raise CredentialError("Storing a token is only supported on Windows.")

    def delete(self, name):
        return None

    def rename(self, old, new):
        return None


if IS_WINDOWS:
    # ctypes.wintypes can only be imported on Windows: it defines types
    # (e.g. VARIANT_BOOL) whose ctypes type codes don't exist elsewhere.
    import ctypes
    import ctypes.wintypes

    _wt = ctypes.wintypes
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", _wt.DWORD), ("dwHighDateTime", _wt.DWORD)]

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", _wt.DWORD),
            ("Type", _wt.DWORD),
            ("TargetName", _wt.LPWSTR),
            ("Comment", _wt.LPWSTR),
            ("LastWritten", _FILETIME),
            ("CredentialBlobSize", _wt.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", _wt.DWORD),
            ("AttributeCount", _wt.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", _wt.LPWSTR),
            ("UserName", _wt.LPWSTR),
        ]

    _PCREDENTIAL = ctypes.POINTER(_CREDENTIAL)
    _advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _CredReadW = _advapi32.CredReadW
    _CredReadW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD, ctypes.POINTER(_PCREDENTIAL)]
    _CredReadW.restype = _wt.BOOL
    _CredWriteW = _advapi32.CredWriteW
    _CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), _wt.DWORD]
    _CredWriteW.restype = _wt.BOOL
    _CredDeleteW = _advapi32.CredDeleteW
    _CredDeleteW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD]
    _CredDeleteW.restype = _wt.BOOL
    _CredFree = _advapi32.CredFree
    _CredFree.argtypes = [ctypes.c_void_p]
    _CredFree.restype = None

    class WindowsCredentialStore:
        """Windows Credential Manager, Generic credentials, one per profile."""

        available = True

        def get(self, name):
            pointer = _PCREDENTIAL()
            if not _CredReadW(target_name(name), _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
                error = ctypes.get_last_error()
                if error == _ERROR_NOT_FOUND:
                    return None
                raise CredentialError(str(ctypes.WinError(error)))
            try:
                cred = pointer.contents
                blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
                return {"username": cred.UserName or "", "token": blob.decode("utf-16-le")}
            finally:
                _CredFree(pointer)

        def set(self, name, username, token):
            if not token:
                raise CredentialError("The token is empty.")
            blob = token.encode("utf-16-le")
            buffer = ctypes.create_string_buffer(blob)
            cred = _CREDENTIAL()
            cred.Flags = 0
            cred.Type = _CRED_TYPE_GENERIC
            cred.TargetName = target_name(name)
            cred.Comment = None
            cred.LastWritten = _FILETIME(0, 0)
            cred.CredentialBlobSize = len(blob)
            cred.CredentialBlob = ctypes.cast(buffer, ctypes.c_void_p)
            cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
            cred.AttributeCount = 0
            cred.Attributes = None
            cred.TargetAlias = None
            cred.UserName = username or ""
            if not _CredWriteW(ctypes.byref(cred), 0):
                raise CredentialError(str(ctypes.WinError(ctypes.get_last_error())))

        def delete(self, name):
            if not _CredDeleteW(target_name(name), _CRED_TYPE_GENERIC, 0):
                error = ctypes.get_last_error()
                if error != _ERROR_NOT_FOUND:
                    raise CredentialError(str(ctypes.WinError(error)))

        def rename(self, old, new):
            item = self.get(old)
            if item is None:
                return
            self.set(new, item["username"], item["token"])
            self.delete(old)


def default_store() -> CredentialStore:
    """The credential store for this platform."""
    if IS_WINDOWS:
        return WindowsCredentialStore()
    return UnavailableCredentialStore()


__all__ = [
    "CredentialError",
    "CredentialStore",
    "MemoryCredentialStore",
    "UnavailableCredentialStore",
    "default_store",
    "target_name",
]
