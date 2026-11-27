"""Checks run on exported files before anything is pushed.

These are **basic file checks**: each requested file exists, can be read,
isn't empty or too large, has a unique name, and starts the way its format
requires (for example, a STEP file's ``ISO-10303-21`` header). They catch a
failed or truncated export. They do **not** prove the file opens correctly
in a CAD program or restores the design; that is checked by hand (see
tests/MANUAL_CHECKLIST.md). No Fusion dependency.

Policy (S4): if any requested export fails a check, the whole push is
cancelled. A partial backup is never published and HISTORY.md isn't updated.
"""

from __future__ import annotations

import os
import struct
from typing import Dict, List, Optional, Sequence

from .portable_names import case_collisions

SIZE_LIMIT_BYTES = 100 * 1024 * 1024  # GitHub rejects files of 100 MB or more

FORMAT_EXTENSIONS = {
    "f3d": (".f3d",),
    "f3z": (".f3z",),
    "step": (".step", ".stp"),
    "stl": (".stl",),
    "iges": (".iges", ".igs"),
    "sat": (".sat",),
}


def _head(path: str, size: int = 512) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(size)


def _check_signature(path: str, fmt: str) -> Optional[str]:
    head = _head(path)
    if fmt in ("f3d", "f3z"):
        # Fusion archives are ZIP files.
        if not head.startswith(b"PK\x03\x04"):
            return "is not a Fusion archive (it doesn't have the ZIP header Fusion files start with)"
    elif fmt == "step":
        if not head.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"ISO-10303-21"):
            return "is not a STEP file (missing the ISO-10303-21 header)"
    elif fmt == "stl":
        size = os.path.getsize(path)
        if head[:5].lower() == b"solid" and b"facet" in _head(path, 4096).lower():
            return None  # ASCII STL
        if size >= 84:
            (count,) = struct.unpack("<I", _head(path, 84)[80:84])
            if size == 84 + 50 * count:
                return None  # binary STL: header + 50 bytes per triangle
            return f"is not a complete STL file (expected {84 + 50 * count} bytes for {count} triangles, found {size})"
        return "is too short to be an STL file"
    elif fmt == "iges":
        first_line = head.split(b"\n", 1)[0].rstrip(b"\r")
        if len(first_line) < 73 or first_line[72:73] not in (b"S", b"G"):
            return "is not an IGES file (the first line isn't an IGES start record)"
    elif fmt == "sat":
        if b"\x00" in head:
            return "is not a text SAT file"
    return None


def check_export(path: str, fmt: str) -> Optional[str]:
    """One file: return a plain-language problem, or None if it passes the basic checks."""
    name = os.path.basename(path)
    if not os.path.isfile(path):
        return f"{name} was not created"
    try:
        size = os.path.getsize(path)
        if size == 0:
            return f"{name} is empty"
        if size >= SIZE_LIMIT_BYTES:
            return f"{name} is {size / 1048576:.0f} MB; GitHub rejects files of 100 MB or more"
        extensions = FORMAT_EXTENSIONS.get(fmt, ())
        if extensions and not name.lower().endswith(extensions):
            return f"{name} doesn't have a {fmt.upper()} file extension"
        problem = _check_signature(path, fmt)
    except OSError as exc:
        return f"{name} can't be read ({exc})"
    return f"{name} {problem}" if problem else None


def check_exports(files_by_format: Dict[str, Sequence[str]], requested: Sequence[str]) -> List[str]:
    """Every requested format must have produced files, and every file must pass.

    Returns the problems (empty when everything passed). Any problem means
    the push must not go ahead.
    """
    problems: List[str] = []
    for fmt in requested:
        paths = list(files_by_format.get(fmt) or [])
        if not paths:
            problems.append(f"The {fmt.upper()} export produced no file")
            continue
        for path in paths:
            problem = check_export(path, fmt)
            if problem:
                problems.append(problem)
    all_names = [os.path.basename(p) for paths in files_by_format.values() for p in paths]
    for group in case_collisions(all_names):
        problems.append(
            "These files would overwrite each other on Windows and macOS: " + ", ".join(sorted(group))
        )
    return problems


__all__ = ["FORMAT_EXTENSIONS", "SIZE_LIMIT_BYTES", "check_export", "check_exports"]
