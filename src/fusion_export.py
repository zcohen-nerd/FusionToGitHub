"""Exporting the active Fusion design: formats, file names, design identity.

These functions use the Fusion API (``adsk``) and must run on Fusion's main
thread. They are exercised outside Fusion through the test doubles in
tests/fakes, which simulate the API; that is not a substitute for checking
exports in Fusion itself (tests/MANUAL_CHECKLIST.md).

Policy (S4):

- Every requested export must succeed and pass the basic file checks in
  ``export_checks``; otherwise :class:`ExportResult` lists failures and the
  caller pushes nothing. A partial backup is never published.
- File names are deterministic and portable (``portable_names``), and no two
  files can overwrite each other, even on case-insensitive file systems.
- Linked (externally referenced) components are detected before the
  export. For such a design the Fusion archive is requested as ``.f3z``,
  Fusion's format for a design with its references (risk R-06): Fusion's
  archive export is documented only for ``.f3d``, but an add-in that asks
  ``createFusionArchiveExportOptions`` for an ``.f3z`` name receives one, which
  Fusion writes as ``Name.f3z.f3d`` (community report, fusion-export issue
  #33), so the name is corrected. If that fails, the add-in falls back to
  ``.f3d``. Either way the user is told the backup may not restore on its
  own until restoring one has been verified in Fusion.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .export_checks import check_exports
from .portable_names import portable_name, unique_names

try:
    import adsk.core
    import adsk.fusion
except ImportError:  # pragma: no cover - only outside Fusion without the fakes
    pass

STL_SINGLE = "single"
STL_PER_BODY = "perBody"

# STEP has no settings: Fusion's STEPExportOptions has no protocol choice,
# so the AP203/AP214 option earlier versions showed did nothing (audit
# BUG-03). A saved "step": {"protocol": ...} is ignored.
FORMAT_SETTINGS_DEFAULT = {
    "stl": {"meshRefinement": "high", "files": STL_SINGLE},
}

# format -> setting key -> [(label shown in the dialog, stored value)]
FORMAT_SETTINGS_OPTIONS = {
    "stl": {
        "meshRefinement": [
            ("High (refined mesh)", "high"),
            ("Medium", "medium"),
            ("Low (fast)", "low"),
        ],
        "files": [
            ("One file", STL_SINGLE),
            ("One file per body", STL_PER_BODY),
        ],
    },
}

# Row labels in the dialog's settings table; the default is the format name.
FORMAT_SETTING_LABELS = {("stl", "files"): "STL files"}

AVAILABLE_FORMATS = ["f3d", "step", "iges", "sat", "stl"]
DEFAULT_FORMATS = ["f3d", "step", "stl"]

# What each format is for, as shown in the dialog's "Files to include" list
# (audit UX-06). The stored settings keep the short codes.
FORMAT_CHOICE_LABELS = {
    "f3d": "Fusion design (.f3d): the full editable design",
    "step": "STEP (.step): for other CAD programs",
    "iges": "IGES (.igs): for older CAD programs",
    "sat": "SAT (.sat): ACIS solid model",
    "stl": "STL (.stl, millimetres): for 3D printing",
}


def format_from_choice(label: str) -> str:
    """The format code for a "Files to include" label (or a code)."""
    for code, text in FORMAT_CHOICE_LABELS.items():
        if label in (text, code):
            return code
    return label

# Spellings saved configurations may use for the same format.
FORMAT_ALIASES = {"stp": "step", "igs": "iges"}
SUPPORTED_FORMATS = ("f3d", "step", "iges", "sat", "stl")

# File names are capped below the usual 255-character limit so a design
# folder plus file name still fits comfortably in a Windows path.
MAX_FILE_STEM = 120

STL_UNITS_WARNING = (
    "STL files have no units. This version of Fusion can't be told to write millimetres, "
    "so the STL files use the design's units; check the scale when you import them."
)


@dataclass
class ExportResult:
    """What an export produced. Push only when :attr:`ok` is true."""

    files_by_format: Dict[str, List[str]] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # Display names of linked (externally referenced) components, deduped.
    linked_components: List[str] = field(default_factory=list)
    # "f3z" when the Fusion archive of a design with linked components was
    # written as .f3z (R-06); "f3d" otherwise.
    archive_format: str = "f3d"

    @property
    def files(self) -> List[str]:
        return [path for paths in self.files_by_format.values() for path in paths]

    @property
    def ok(self) -> bool:
        return not self.failures and bool(self.files)


@contextmanager
def temporary_export_dir(parent_dir: Optional[str] = None):
    # Defaults to the system temp folder: exports never go into the
    # repository's working tree; git reads them straight from here.
    temp_path = tempfile.mkdtemp(prefix="fusion_export_", dir=parent_dir)
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


def determine_valid_export_formats(design, requested_formats: list) -> tuple:
    valid = []
    warnings = []
    for fmt in [f.lower() for f in requested_formats]:
        if fmt in ("dwg", "dxf"):
            # Fusion's design ExportManager offers no DWG/DXF export; these
            # formats were previously listed but never produced a file.
            # Saved configurations may still request them.
            warnings.append(f"{fmt.upper()} skipped: not supported by the Fusion design export API.")
            continue
        valid.append(fmt)
    return valid, warnings


def get_fusion_design(app, logger: Optional[logging.Logger] = None):
    """The active product if it is a Fusion design, else None."""
    try:
        if not app:
            if logger:
                logger.warning("get_fusion_design called without a Fusion application.")
            return None
        product = app.activeProduct
        is_design = product and product.objectType == adsk.fusion.Design.classType()
        return product if is_design else None
    except Exception:
        if logger:
            logger.exception("Error in get_fusion_design")
        return None


def _safe_base(name: str) -> str:
    name = re.sub(r"\s+v[\dA-Za-z]+$", "", name).strip()  # drop trailing " v8" etc.
    # keep spaces; just neutralize illegal filesystem chars
    return re.sub(r'[<>:"/\\|?*]+', "_", name)


def design_identity(design) -> Tuple[str, str]:
    """Return (display name, stable id) for a design.

    The id is the cloud document's ``dataFile.id`` when the design has been
    saved, which survives renames; an unsaved design falls back to its name.
    """
    display_name = _safe_base(design.rootComponent.name)
    design_id = ""
    try:
        document = design.parentDocument
        data_file = document.dataFile if document else None
        design_id = (data_file.id if data_file else "") or ""
    except Exception:
        design_id = ""
    return display_name, (design_id or f"name:{display_name}")


# ----------------------------------------------------------------------
# Walking the design (every access guarded: Fusion can raise on nested
# references and on components that failed to load)
# ----------------------------------------------------------------------


def design_version_text(design) -> str:
    """Which Fusion version of the design is backed up, in words ("v12", "v12 with unsaved changes").

    "not saved yet" for a design that was never saved; "" if Fusion doesn't
    say. Recorded in HISTORY.md and shown in the dialog and the summary.
    """
    try:
        document = design.parentDocument
        data_file = document.dataFile if document else None
        if data_file is None:
            return "not saved yet"
        number = getattr(data_file, "versionNumber", None)
        text = f"v{number}" if isinstance(number, int) and number > 0 else "saved"
        if getattr(document, "isModified", False) is True:
            text += " with unsaved changes"
        return text
    except Exception:
        return ""


def _items(collection) -> list:
    """The members of a Fusion collection (``count``/``item``), or [] if it can't be read."""
    if collection is None:
        return []
    try:
        return [collection.item(i) for i in range(collection.count)]
    except Exception:
        try:
            return list(collection)
        except Exception:
            return []


def _attr(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _occurrence_label(occurrence) -> str:
    component = _attr(occurrence, "component")
    return str(_attr(component, "name") or _attr(occurrence, "name") or "unnamed component")


def find_linked_components(design, logger: Optional[logging.Logger] = None) -> Tuple[List[str], List[str]]:
    """Return (linked component names, warnings).

    A linked component is one inserted from another Fusion document
    (``Occurrence.isReferencedComponent``). Its geometry may not be inside
    the ``.f3d`` export, so the backup might not restore on its own.
    """
    names: List[str] = []
    unknown: List[str] = []
    root = _attr(design, "rootComponent")
    occurrences = _attr(root, "allOccurrences")
    if root is None or occurrences is None:
        return [], ["Couldn't check this design for linked components."]
    for occurrence in _items(occurrences):
        try:
            linked = bool(occurrence.isReferencedComponent)
        except Exception:
            if logger:
                logger.debug("isReferencedComponent failed", exc_info=True)
            unknown.append(_occurrence_label(occurrence))
            continue
        if linked:
            label = _occurrence_label(occurrence)
            if label not in names:
                names.append(label)
    warnings = []
    if unknown:
        warnings.append(
            "Couldn't tell whether these components are linked from other designs: "
            + ", ".join(sorted(set(unknown)))
        )
    return names, warnings


def _occurrence_path(occurrence) -> List[str]:
    """Names from the root to *occurrence* ("Arm:1+Bolt:2" -> ["Arm 1", "Bolt 2"])."""
    full = _attr(occurrence, "fullPathName") or _attr(occurrence, "name") or "Component"
    return [part.replace(":", " ") for part in str(full).split("+") if part]


def _visible(body) -> bool:
    value = _attr(body, "isVisible", True)
    return True if value is None else bool(value)


def stl_bodies(design) -> Tuple[List[Tuple[List[str], object]], int]:
    """Visible bodies to export one STL each: ([(occurrence path, body)], hidden count).

    Root bodies have an empty path. Bodies inside components come from each
    occurrence's ``bRepBodies`` (Fusion returns proxies in assembly context).
    """
    root = design.rootComponent
    found: List[Tuple[List[str], object]] = []
    hidden = 0
    for body in _items(_attr(root, "bRepBodies")):
        if _visible(body):
            found.append(([], body))
        else:
            hidden += 1
    for occurrence in _items(_attr(root, "allOccurrences")):
        path = _occurrence_path(occurrence)
        for body in _items(_attr(occurrence, "bRepBodies")):
            if _visible(body):
                found.append((path, body))
            else:
                hidden += 1
    return found, hidden


def per_body_file_names(base: str, bodies: List[Tuple[List[str], object]]) -> List[str]:
    """Deterministic, unique (ignoring case) STL file names, one per body.

    Root bodies: ``"<design> - <body>.stl"``; bodies in components:
    ``"<design> - <occurrence path> - <body>.stl"``.
    """
    names = []
    for path, body in bodies:
        body_name = str(_attr(body, "name") or "Body")
        stem = " - ".join([base, *path, body_name])
        names.append(portable_name(stem, fallback="Body", max_length=MAX_FILE_STEM) + ".stl")
    return unique_names(names)


# ----------------------------------------------------------------------
# Export options
# ----------------------------------------------------------------------


def _mesh_refinement(settings: Dict[str, str]):
    refinement = (settings.get("meshRefinement") or FORMAT_SETTINGS_DEFAULT["stl"]["meshRefinement"]).lower()
    refinement_map = {
        "high": adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
        "medium": adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
        "low": adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
    }
    return refinement_map.get(refinement, adsk.fusion.MeshRefinementSettings.MeshRefinementHigh)


def _set_stl_millimetres(options) -> bool:
    """Ask Fusion for millimetres; False when this Fusion version can't do it."""
    units = getattr(getattr(adsk.fusion, "DistanceUnits", None), "MillimeterDistanceUnits", None)
    if units is None or not hasattr(options, "unitType"):
        return False
    try:
        options.unitType = units
        return True
    except Exception:
        return False


def _stl_options(em, geometry, path, settings, result: ExportResult):
    options = em.createSTLExportOptions(geometry, path)
    options.meshRefinement = _mesh_refinement(settings)
    if not _set_stl_millimetres(options) and STL_UNITS_WARNING not in result.warnings:
        result.warnings.append(STL_UNITS_WARNING)
    return options


def _options_for(em, root, fmt: str, path: str, settings: Dict[str, str], logger):
    if fmt == "f3d":
        try:
            return em.createFusionArchiveExportOptions(path)
        except TypeError:
            return em.createFusionArchiveExportOptions(path, root)
    if fmt == "step":
        return em.createSTEPExportOptions(path, root)
    if fmt == "iges":
        return em.createIGESExportOptions(path, root)
    return em.createSATExportOptions(path, root)


def _archive_written_as(path: str) -> Optional[str]:
    """Where Fusion put an archive requested as *path* (an .f3z), renamed to *path* if needed.

    Fusion appends ".f3d" to archive file names, so "Name.f3z" can arrive
    as "Name.f3z.f3d". None if neither exists.
    """
    if os.path.isfile(path):
        return path
    appended = path + ".f3d"
    if os.path.isfile(appended):
        os.replace(appended, path)
        return path
    return None


def _export_f3z(em, root, path: str, logger) -> Tuple[bool, str]:
    """Try the archive as .f3z (R-06): (True, "") or (False, why it didn't work)."""
    try:
        options = _options_for(em, root, "f3d", path, {}, logger)
        if not em.execute(options):
            return False, "Fusion reported that the .f3z export failed"
    except Exception as exc:
        return False, f"the .f3z export failed: {exc}"
    if _archive_written_as(path) is None:
        return False, "Fusion didn't write an .f3z file"
    return True, ""


def _run(em, options, fmt: str, path: str, result: ExportResult, logger) -> bool:
    """Execute one export; record a failure and return False if Fusion reports one."""
    name = os.path.basename(path)
    try:
        succeeded = em.execute(options)
    except Exception as exc:
        if logger:
            logger.exception("Export error for %s", name)
        result.failures.append(f"The {fmt.upper()} export of {name} failed: {exc}")
        return False
    if not succeeded:
        if logger:
            logger.warning("Fusion reported a failed export: %s", name)
        result.failures.append(f"Fusion reported that the {fmt.upper()} export of {name} failed")
        return False
    if logger and os.path.exists(path):
        logger.info("Exported: %s (%d bytes)", path, os.path.getsize(path))
    return True


# ----------------------------------------------------------------------
# The export
# ----------------------------------------------------------------------


def export_design(
    design,
    temp_dir: str,
    base_name: str,
    formats,
    format_settings: Optional[Dict[str, Dict[str, str]]] = None,
    logger: Optional[logging.Logger] = None,
) -> ExportResult:
    """Export *design* in each requested format into *temp_dir*.

    Never raises for a failed export: failures are collected in the result,
    and the caller must not push unless ``result.ok``. Every file is checked
    with ``export_checks.check_exports`` (basic validation, not proof that
    the file restores the design).
    """
    result = ExportResult()
    settings = format_settings or {}
    base = portable_name(base_name, fallback="Design", max_length=MAX_FILE_STEM)
    em = design.exportManager
    root = design.rootComponent

    requested: List[Tuple[str, str]] = []  # (canonical format, file extension)
    for raw in formats or []:
        ext = str(raw).lower().strip()
        fmt = FORMAT_ALIASES.get(ext, ext)
        if fmt not in SUPPORTED_FORMATS:
            result.warnings.append(f"{ext.upper()} skipped: this add-in can't export that format.")
            continue
        if (fmt, ext) not in requested:
            requested.append((fmt, ext))

    if any(fmt == "f3d" for fmt, _ in requested):
        linked, warnings = find_linked_components(design, logger)
        result.linked_components = linked
        result.warnings.extend(warnings)

    succeeded: List[str] = []
    for fmt, ext in requested:
        fmt_settings = settings.get(fmt) or settings.get(ext) or {}
        written: List[str] = []
        ok = True
        if fmt == "f3d" and result.linked_components:
            f3z_path = os.path.join(temp_dir, f"{base}.f3z")
            done, why = _export_f3z(em, root, f3z_path, logger)
            if done:
                result.archive_format = "f3z"
                result.files_by_format.setdefault("f3z", []).append(f3z_path)
                succeeded.append("f3z")
                if logger:
                    logger.info("Exported the design with its linked components as %s", f3z_path)
                continue
            for leftover in (f3z_path, f3z_path + ".f3d"):
                if os.path.isfile(leftover):
                    os.remove(leftover)
            result.warnings.append(
                f"The design has linked components, but Fusion couldn't write an .f3z archive ({why}), "
                "so the backup has an .f3d file instead."
            )
        try:
            if fmt == "stl" and fmt_settings.get("files") == STL_PER_BODY:
                bodies, hidden = stl_bodies(design)
                if not bodies:
                    result.failures.append("The STL export found no visible bodies to export one file per body")
                    continue
                if hidden:
                    result.warnings.append(f"{hidden} hidden bodies were not exported as STL files.")
                for (_, body), name in zip(bodies, per_body_file_names(base, bodies)):
                    path = os.path.join(temp_dir, name)
                    options = _stl_options(em, body, path, fmt_settings, result)
                    ok = _run(em, options, fmt, path, result, logger) and ok
                    written.append(path)
            else:
                path = os.path.join(temp_dir, f"{base}.{ext}")
                if fmt == "stl":
                    options = _stl_options(em, root, path, fmt_settings, result)
                else:
                    options = _options_for(em, root, fmt, path, fmt_settings, logger)
                ok = _run(em, options, fmt, path, result, logger)
                written.append(path)
        except Exception as exc:  # setting up the options failed
            if logger:
                logger.exception("Export setup failed for %s", fmt)
            result.failures.append(f"The {fmt.upper()} export couldn't be prepared: {exc}")
            continue
        if ok:
            result.files_by_format.setdefault(fmt, []).extend(written)
            succeeded.append(fmt)

    result.failures.extend(check_exports(result.files_by_format, list(dict.fromkeys(succeeded))))
    return result


def linked_components_question(names: List[str], archive_format: str = "f3d") -> str:
    shown = ", ".join(names[:5]) + (f", and {len(names) - 5} more" if len(names) > 5 else "")
    count = len(names)
    noun = "linked component" if count == 1 else "linked components"
    if archive_format == "f3z":
        how = ("The design was exported as an .f3z archive, Fusion's format for a design with linked "
               "components, but restoring one hasn't been verified yet, so this backup might not restore "
               "on its own. Keep the linked designs in Fusion too.")
    else:
        how = "Fusion's .f3d export may not include them, so this backup might not restore on its own."
    return f"This design uses {count} {noun} ({shown}).\n\n{how} Push anyway?"


def linked_components_note(names: List[str], archive_format: str = "f3d") -> str:
    count = len(names)
    noun = "linked component" if count == 1 else "linked components"
    if archive_format == "f3z":
        return (f"Contains {count} {noun} ({', '.join(names)}); exported as .f3z, but restoring it hasn't "
                "been verified, so this backup may not be self-contained.")
    return f"Contains {count} {noun} ({', '.join(names)}); this .f3d backup may not be self-contained."


__all__ = [
    "AVAILABLE_FORMATS",
    "DEFAULT_FORMATS",
    "FORMAT_CHOICE_LABELS",
    "design_version_text",
    "format_from_choice",
    "ExportResult",
    "FORMAT_SETTINGS_DEFAULT",
    "FORMAT_SETTINGS_OPTIONS",
    "FORMAT_SETTING_LABELS",
    "STL_PER_BODY",
    "STL_SINGLE",
    "design_identity",
    "determine_valid_export_formats",
    "export_design",
    "find_linked_components",
    "get_fusion_design",
    "linked_components_note",
    "linked_components_question",
    "per_body_file_names",
    "stl_bodies",
    "temporary_export_dir",
]
