"""Exporting the active Fusion design: formats, file names, design identity.

These functions use the Fusion API (``adsk``) and must run on Fusion's main
thread. They are exercised outside Fusion through the test doubles in
tests/fakes, which simulate the API; that is not a substitute for checking
exports in Fusion itself.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from typing import List, Optional, Tuple

try:
    import adsk.core
    import adsk.fusion
except ImportError:  # pragma: no cover - only outside Fusion without the fakes
    pass

FORMAT_SETTINGS_DEFAULT = {
    "stl": {"meshRefinement": "high"},
    "step": {"protocol": "AP214"},
}

FORMAT_SETTINGS_OPTIONS = {
    "stl": [
        ("High (refined mesh)", "high"),
        ("Medium", "medium"),
        ("Low (fast)", "low"),
    ],
    "step": [
        ("AP203", "AP203"),
        ("AP214 (default)", "AP214"),
    ],
}

AVAILABLE_FORMATS = ["f3d", "step", "iges", "sat", "stl"]
DEFAULT_FORMATS = ["f3d", "step", "stl"]


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


def export_fusion_design(
    design,
    export_dir: str,
    base_name: str,
    formats_to_export: list,
    target_ui_ref,
    format_settings=None,
    title: str = "Push to GitHub",
    logger: Optional[logging.Logger] = None,
) -> List[str]:
    """Export *design* in each format into *export_dir*; return the files that were written."""
    em = design.exportManager
    root = design.rootComponent
    exported = []
    format_settings = format_settings or {}

    def file_ok(p):
        return os.path.exists(p) and os.path.getsize(p) > 0

    for fmt in [f.lower() for f in formats_to_export]:
        path = os.path.join(export_dir, f"{base_name}.{fmt}")
        try:
            opts = None
            if fmt == "f3d":
                try:
                    opts = em.createFusionArchiveExportOptions(path)
                except TypeError:
                    opts = em.createFusionArchiveExportOptions(path, root)
            elif fmt in ("step", "stp"):
                opts = em.createSTEPExportOptions(path, root)
            elif fmt in ("iges", "igs"):
                opts = em.createIGESExportOptions(path, root)
            elif fmt == "sat":
                opts = em.createSATExportOptions(path, root)
            elif fmt == "stl":
                opts = em.createSTLExportOptions(root, path)
                refinement = format_settings.get("stl", {}).get(
                    "meshRefinement",
                    FORMAT_SETTINGS_DEFAULT.get("stl", {}).get("meshRefinement", "high"),
                )
                refinement = (refinement or "high").lower()
                refinement_map = {
                    "high": adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
                    "medium": adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
                    "low": adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
                }
                opts.meshRefinement = refinement_map.get(
                    refinement, adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
                )
            else:
                if logger:
                    logger.warning("Unsupported/unavailable export format: %s", fmt)
                continue

            if fmt in ("step", "stp") and opts:
                protocol = format_settings.get("step", {}).get("protocol", "AP214")
                if hasattr(opts, "applicationProtocol"):
                    try:
                        opts.applicationProtocol = str(protocol)
                    except Exception:
                        if logger:
                            logger.debug("Failed to set STEP protocol to %s.", protocol, exc_info=True)

            if opts and em.execute(opts) and file_ok(path):
                exported.append(path)
                if logger:
                    logger.info("Exported: %s (%d bytes)", path, os.path.getsize(path))
            else:
                target_ui_ref.messageBox(f"Export failed or empty file for {fmt}: {path}", title)
                if logger:
                    logger.warning("Export failed/empty for %s -> %s", fmt, path)
        except Exception:
            if logger:
                logger.exception("Export error for %s", fmt)
            target_ui_ref.messageBox(f"Error exporting {fmt} for '{base_name}'", title)
    return exported
