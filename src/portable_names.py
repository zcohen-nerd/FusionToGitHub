"""File and folder names that work the same on Windows, macOS and GitHub.

Deterministic: the same input always gives the same name, so a design's
files keep their names from push to push. No Fusion dependency.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List

# Device names Windows refuses as a file or folder name, with any extension.
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
    | {"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]+')
_SPACES = re.compile(r"\s+")
MAX_NAME_LENGTH = 100


def portable_name(name: str, fallback: str = "Design", max_length: int = MAX_NAME_LENGTH) -> str:
    """Make *name* safe as one path segment on every supported system.

    - Unicode is normalised (NFC), so the same visible name is the same bytes
      on Windows and macOS.
    - Characters Windows forbids, control characters, and path separators
      become ``_``, so a name can never point into another folder.
    - Runs of whitespace become one space; leading and trailing spaces and
      periods are removed (Windows drops trailing ones silently).
    - Windows device names (CON, NUL, COM1, ...), with or without an
      extension, get a trailing ``_``.
    - ``.`` and ``..`` can't survive, and an empty result becomes *fallback*.
    """
    text = unicodedata.normalize("NFC", name or "")
    text = re.sub(r"[\t\r\n\v\f]+", " ", text)  # whitespace controls are spaces
    text = _UNSAFE.sub("_", text)
    text = _SPACES.sub(" ", text).strip(" .")
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    if not text or set(text) <= {"."}:
        text = fallback
    stem = text.split(".", 1)[0].rstrip(" ")
    if stem.upper() in WINDOWS_RESERVED:
        text = stem + "_" + text[len(stem):]
    return text


def unique_names(names: Iterable[str]) -> List[str]:
    """Give each name a unique spelling, ignoring case ("Part", "part (2)").

    Windows and macOS treat names that differ only in case as the same file,
    so ``Part.stl`` and ``PART.stl`` would overwrite each other. Order is
    kept; the first occurrence keeps its name.
    """
    seen: Dict[str, int] = {}
    result = []
    for name in names:
        candidate = name
        stem, dot, ext = name.rpartition(".") if "." in name else (name, "", "")
        n = 2
        while candidate.casefold() in seen:
            candidate = f"{stem} ({n}){dot}{ext}" if dot else f"{name} ({n})"
            n += 1
        seen[candidate.casefold()] = 1
        result.append(candidate)
    return result


def case_collisions(names: Iterable[str]) -> List[List[str]]:
    """Groups of names that would be the same file on Windows/macOS."""
    groups: Dict[str, List[str]] = {}
    for name in names:
        groups.setdefault(unicodedata.normalize("NFC", name).casefold(), []).append(name)
    return [group for group in groups.values() if len(group) > 1]


__all__ = ["MAX_NAME_LENGTH", "WINDOWS_RESERVED", "case_collisions", "portable_name", "unique_names"]
