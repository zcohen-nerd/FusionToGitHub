"""Push to GitHub (ZAC) — V7.7
Export → changelog → branch → commit → push.
V7.7 formalizes dependency packaging and adds an offline CLI harness.
"""

import adsk.core, adsk.fusion, adsk.cam, traceback
import ctypes
import ctypes.wintypes
import logging
import logging.handlers
import os
import platform
import re
import json
import shutil
import subprocess
import tempfile
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

# Import core functions - handle both standalone and installed scenarios
try:
    from fusion_git_core import (
        VERSION as CORE_VERSION,
        generate_branch_name,
        git_available as core_git_available,
        handle_git_operations as core_handle_git_operations,
        sanitize_branch_name,
    )
except ImportError:
    # Add current directory to path for Fusion 360 add-in installation
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    from fusion_git_core import (
        VERSION as CORE_VERSION,
        generate_branch_name,
        git_available as core_git_available,
        handle_git_operations as core_handle_git_operations,
        sanitize_branch_name,
    )

VERSION = CORE_VERSION
IS_WINDOWS = os.name == 'nt'

# -----------------------------
# Git (CLI) — no GitPython
# -----------------------------
GIT_EXE = shutil.which("git") or r"C:\Program Files\Git\bin\git.exe"
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = GIT_EXE  # harmless if GitPython absent

def _git(repo_path, *args, check=True):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    p = subprocess.run([GIT_EXE, *args], cwd=repo_path, capture_output=True, text=True, creationflags=flags)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{p.stderr or p.stdout}")
    return p

def _git_out(repo_path, *args):
    return (_git(repo_path, *args, check=True).stdout or "").strip()

def _git_available():
    try:
        return core_git_available()
    except Exception:
        return False

# -----------------------------
# Config / constants
# -----------------------------
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")
ADD_NEW_OPTION = "+ Add new GitHub repo..."
META_KEY = "__meta__"

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

LOG_DIR = os.path.expanduser("~/.PushToGitHub_AddIn_Data")
LOG_FILE_PATH = os.path.join(LOG_DIR, "PushToGitHub.log")

CMD_ID = "PushToGitHub_Cmd_ZAC_V7_4"
CMD_NAME = "Push to GitHub (ZAC)"
CMD_TOOLTIP = "Exports/configures, updates changelog, and pushes design to GitHub."
PANEL_ID = "SolidUtilitiesAddinsPanel"
FALLBACK_PANEL_ID = "SolidScriptsAddinsPanel"
CONTROL_ID = CMD_ID + "_Control"


def _has_open_drawing_document() -> bool:
    if not app:
        return False
    try:
        docs = app.documents
        for i in range(docs.count):
            doc = docs.item(i)
            if doc and doc.documentType == adsk.core.DocumentTypes.DrawingDocumentType:
                return True
    except Exception:
        if logger:
            logger.debug("Failed to inspect documents for drawing presence.", exc_info=True)
    return False


def _component_or_children_have_sketches(component: adsk.fusion.Component) -> bool:
    try:
        if component.sketches.count:
            return True
        for occurrence in component.occurrences:
            child = occurrence.component
            if child and _component_or_children_have_sketches(child):
                return True
    except Exception:
        if logger:
            logger.debug("Sketch detection failed for component %s.", getattr(component, "name", "?"), exc_info=True)
    return False


def _design_has_sketches(design: adsk.fusion.Design) -> bool:
    if not design:
        return False
    try:
        root = design.rootComponent
        return _component_or_children_have_sketches(root)
    except Exception:
        if logger:
            logger.debug("Unable to evaluate sketches for design.", exc_info=True)
        return False


@contextmanager
def temporary_export_dir(parent_dir: str):
    temp_path = tempfile.mkdtemp(prefix="fusion_export_", dir=parent_dir)
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


def determine_valid_export_formats(design, requested_formats):
    valid = []
    warnings = []
    has_sketches = None
    has_drawing = None

    for fmt in [f.lower() for f in requested_formats]:
        if fmt == "dwg":
            if has_drawing is None:
                has_drawing = _has_open_drawing_document()
            if not has_drawing:
                warnings.append("DWG skipped: no drawing document is open.")
                continue
        if fmt == "dxf":
            if has_sketches is None:
                has_sketches = _design_has_sketches(design)
            if not has_sketches:
                warnings.append("DXF skipped: design has no sketches to export.")
                continue
        valid.append(fmt)

    return valid, warnings

# -----------------------------
# Globals
# -----------------------------
app = None
ui = None
logger = None
file_log_handler: Optional[logging.Handler] = None
fusion_palette_handler: Optional[logging.Handler] = None
handlers = []
push_cmd_def = None
git_push_control = None
is_initialized = False  # guard against double run()
current_log_level_name = "INFO"

try:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    print(f"[PushToGitHub] Loaded {VERSION} with CMD_ID={CMD_ID}")
except AttributeError:
    pass

class FusionPaletteHandler(logging.Handler):
    """Custom logging handler that outputs to Fusion 360's text palette."""
    
    def __init__(self):
        super().__init__()
        # Try to map to Fusion LogLevels, fallback to basic logging if not available
        try:
            # Try the expected LogLevel enum values
            self.LEVEL_MAP = {
                logging.DEBUG: getattr(adsk.core.LogLevels, 'DebugLogLevel', None),
                logging.INFO: getattr(adsk.core.LogLevels, 'InfoLogLevel', None),
                logging.WARNING: getattr(adsk.core.LogLevels, 'WarningLogLevel', None),
                logging.ERROR: getattr(adsk.core.LogLevels, 'ErrorLogLevel', None),
                logging.CRITICAL: getattr(adsk.core.LogLevels, 'CriticalLogLevel', None),
            }
            # Remove None values (unsupported log levels)
            self.LEVEL_MAP = {k: v for k, v in self.LEVEL_MAP.items() if v is not None}
            
            # If no valid mappings found, try alternative names
            if not self.LEVEL_MAP:
                self.LEVEL_MAP = {
                    logging.INFO: getattr(adsk.core.LogLevels, 'InfoLogLevel', 
                                        getattr(adsk.core.LogLevels, 'Information', None)),
                    logging.WARNING: getattr(adsk.core.LogLevels, 'WarningLogLevel',
                                           getattr(adsk.core.LogLevels, 'Warning', None)),
                    logging.ERROR: getattr(adsk.core.LogLevels, 'ErrorLogLevel',
                                         getattr(adsk.core.LogLevels, 'Error', None)),
                }
                self.LEVEL_MAP = {k: v for k, v in self.LEVEL_MAP.items() if v is not None}
            
        except (AttributeError, NameError):
            # If LogLevels enum is not available, we'll just use app.log without levels
            self.LEVEL_MAP = {}

    def emit(self, record: logging.LogRecord) -> None:
        if not app:
            return
        try:
            message = self.format(record)
            if self.LEVEL_MAP:
                level = self.LEVEL_MAP.get(record.levelno, list(self.LEVEL_MAP.values())[0])
                app.log(message, level)
            else:
                # Fallback: just log the message without level specification
                app.log(message)
        except Exception:
            pass


def _ensure_log_dir_exists() -> bool:
    if os.path.exists(LOG_DIR):
        return True
    try:
        os.makedirs(LOG_DIR)
        return True
    except OSError as exc:
        print(f"Error creating log directory {LOG_DIR}: {exc}. Logging disabled.")
        if app:
            app.log(f"Failed to create log directory {LOG_DIR}: {exc}.", adsk.core.LogLevels.ErrorLogLevel)
        return False


def setup_logger():
    global logger, file_log_handler, fusion_palette_handler
    if logger is not None and logger.handlers:
        return

    if not _ensure_log_dir_exists():
        logger = logging.getLogger(CMD_ID + "_disabled")
        logger.addHandler(logging.NullHandler())
        return

    logger = logging.getLogger(CMD_ID)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_log_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
    )
    file_log_handler.setFormatter(formatter)
    logger.addHandler(file_log_handler)

    # Add Fusion palette handler with error handling for API changes
    try:
        fusion_palette_handler = FusionPaletteHandler()
        fusion_palette_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(fusion_palette_handler)
    except Exception as e:
        # If Fusion palette handler fails, log to file only
        logger.warning(f"Could not initialize Fusion palette logging: {e}")

    set_logger_level(current_log_level_name)
    logger.info(f"'{CMD_NAME}' Logger initialized. Log file: {LOG_FILE_PATH}")


def set_logger_level(level_name: str):
    global current_log_level_name
    if not logger:
        return
    normalized = (level_name or "INFO").upper()
    mapped_level = getattr(logging, normalized, logging.INFO)
    current_log_level_name = normalized
    if file_log_handler:
        file_log_handler.setLevel(mapped_level)
    if fusion_palette_handler:
        fusion_palette_handler.setLevel(mapped_level)
    logger.debug("Logger level updated to %s", normalized)


def open_log_file(target_ui_ref) -> None:
    if not os.path.exists(LOG_FILE_PATH):
        if target_ui_ref:
            target_ui_ref.messageBox(
                "Log file not found yet. Run a push to generate logs first.",
                CMD_NAME,
            )
        return

    try:
        if IS_WINDOWS:
            os.startfile(LOG_FILE_PATH)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", LOG_FILE_PATH])
        else:
            subprocess.Popen(["xdg-open", LOG_FILE_PATH])
    except Exception as exc:
        if target_ui_ref:
            target_ui_ref.messageBox(
                f"Unable to open log file automatically.\nPath: {LOG_FILE_PATH}\nError: {exc}",
                CMD_NAME,
            )
        if logger:
            logger.error("Failed to open log file: %s", exc, exc_info=True)


# -----------------------------
# Windows Credential Manager helpers (PAT)
# -----------------------------
if IS_WINDOWS:
    wintypes = ctypes.wintypes

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIAL = ctypes.POINTER(CREDENTIAL)
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    CredReadW = advapi32.CredReadW
    CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIAL)]
    CredReadW.restype = wintypes.BOOL

    CredWriteW = advapi32.CredWriteW
    CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    CredWriteW.restype = wintypes.BOOL

    CredDeleteW = advapi32.CredDeleteW
    CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    CredDeleteW.restype = wintypes.BOOL

    CredFree = advapi32.CredFree
    CredFree.argtypes = [ctypes.c_void_p]
    CredFree.restype = None


def _credential_target(repo_identifier: str) -> str:
    return f"FusionToGitHub::{repo_identifier}"


def read_stored_pat(repo_identifier: str) -> Optional[dict]:
    if not IS_WINDOWS:
        return None

    target_name = _credential_target(repo_identifier)
    credential_pp = PCREDENTIAL()
    success = CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(credential_pp))
    if not success:
        error_code = ctypes.get_last_error()
        if error_code == ERROR_NOT_FOUND:
            return None
        raise ctypes.WinError(error_code)

    try:
        credential = credential_pp.contents
        blob_size = credential.CredentialBlobSize
        blob = ctypes.string_at(credential.CredentialBlob, blob_size)
        token = blob.decode("utf-16-le")
        username = credential.UserName or ""
        return {"username": username, "token": token}
    finally:
        CredFree(credential_pp)


def store_pat(repo_identifier: str, username: str, token: str) -> None:
    if not IS_WINDOWS:
        raise RuntimeError("PAT storage is only supported on Windows.")
    target_name = _credential_target(repo_identifier)
    blob = token.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)

    credential = CREDENTIAL()
    credential.Flags = 0
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target_name
    credential.Comment = None
    credential.LastWritten = FILETIME(0, 0)
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.c_void_p)
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = username or ""

    if not CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_pat(repo_identifier: str) -> None:
    if not IS_WINDOWS:
        return
    target_name = _credential_target(repo_identifier)
    success = CredDeleteW(target_name, CRED_TYPE_GENERIC, 0)
    if not success:
        error_code = ctypes.get_last_error()
        if error_code == ERROR_NOT_FOUND:
            return
        raise ctypes.WinError(error_code)

# -----------------------------
# Toolbar helpers (dedupe)
# -----------------------------
def _find_control_anywhere(control_id: str):
    if not ui:
        return None, None
    for i in range(ui.allToolbarPanels.count):
        panel = ui.allToolbarPanels.item(i)
        try:
            ctrl = panel.controls.itemById(control_id)
            if ctrl and ctrl.isValid:
                return ctrl, panel
        except:
            pass
    return None, None

def _delete_all_controls(control_id: str):
    if not ui:
        return
    for i in range(ui.allToolbarPanels.count):
        panel = ui.allToolbarPanels.item(i)
        try:
            ctrl = panel.controls.itemById(control_id)
            if ctrl and ctrl.isValid:
                ctrl.deleteMe()
        except:
            pass

# -----------------------------
# Helpers
# -----------------------------
def check_git_available(target_ui_ref):
    if _git_available():
        return True
    msg = "Git executable not found or not working. Check PATH or install Git."
    target_ui_ref.messageBox(msg, "Git Not Found")
    if logger: logger.error(msg)
    return False

def load_config():
    global logger, ui
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({}, f)
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        final_ui_ref = ui or (app.userInterface if app else None)
        backup_path = CONFIG_PATH + ".bak_corrupted_" + datetime.now().strftime("%Y%m%d%H%M%S")
        try:
            if os.path.exists(CONFIG_PATH):
                shutil.copyfile(CONFIG_PATH, backup_path)
        finally:
            msg = f"Config file corrupt. Backup at:\n{backup_path}\nNew config created."
            if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
            if logger: logger.error(msg)
            with open(CONFIG_PATH, 'w') as f:
                json.dump({}, f)
        return {}
    except Exception as e:
        msg = f"Error loading config '{CONFIG_PATH}': {str(e)}"
        final_ui_ref = ui or (app.userInterface if app else None)
        if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
        if logger: logger.error(msg, exc_info=True)
        return {}

def save_config(config_data):
    global logger, ui
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=4)
        if logger: logger.info(f"Configuration saved to {CONFIG_PATH}")
    except Exception as e:
        msg = f"Failed to save configuration: {str(e)}"
        final_ui_ref = ui or (app.userInterface if app else None)
        if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
        if logger: logger.error(msg, exc_info=True)

def get_fusion_design():
    global app, logger
    try:
        if not app:
            if logger: logger.warning("get_fusion_design called but global 'app' is None.")
            return None
        product = app.activeProduct
        return product if product and product.objectType == adsk.fusion.Design.classType() else None
    except:
        if logger: logger.exception("Error in get_fusion_design")
        return None

def _safe_base(name: str) -> str:
    name = re.sub(r'\s+v[\dA-Za-z]+$', '', name).strip()   # drop trailing " v8" etc.
    # keep spaces; just neutralize illegal filesystem chars
    return re.sub(r'[<>:"/\\|?*]+', '_', name)


def normalize_export_subfolder(raw: str) -> str:
    value = (raw or "").strip().replace("\\", "/")
    if not value:
        return ""
    if value.startswith("/"):
        raise ValueError("Export subfolder must be relative (no leading slash).")
    parts = [segment.strip() for segment in value.split("/") if segment.strip()]
    if not parts:
        return ""
    invalid = {"..", "."}
    for segment in parts:
        if segment in invalid:
            raise ValueError("Export subfolder cannot contain '..' or '.' segments.")
        if re.search(r'[<>:"\\|?*]', segment):
            raise ValueError(f"Invalid characters in subfolder segment '{segment}'.")
    return "/".join(parts)


def ensure_export_subfolder_exists(repo_path: str, relative_subfolder: str) -> str:
    if not relative_subfolder:
        return repo_path
    dest = os.path.normpath(os.path.join(repo_path, relative_subfolder))
    if not dest.startswith(os.path.normpath(repo_path)):
        raise ValueError("Export subfolder resolves outside the repository root.")
    os.makedirs(dest, exist_ok=True)
    return dest


class FusionCommandGitUI:
    def __init__(self, ui_ref: Optional[adsk.core.UserInterface]):
        self._ui = ui_ref

    def info(self, message: str) -> None:
        if logger:
            logger.info(message)
        elif app:
            app.log(message, adsk.core.LogLevels.InfoLogLevel)

    def warn(self, message: str) -> None:
        if logger:
            logger.warning(message)
        elif app:
            app.log(message, adsk.core.LogLevels.WarningLogLevel)

    def error(self, message: str) -> None:
        if logger:
            logger.error(message)
        ui_ref = self._ui or (app.userInterface if app else None)
        if ui_ref:
            ui_ref.messageBox(message, CMD_NAME)

    def confirm(self, message: str) -> bool:
        ui_ref = self._ui or (app.userInterface if app else None)
        if not ui_ref:
            return False
        result = ui_ref.messageBox(
            message,
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        )
        return result == adsk.core.DialogResults.DialogYes


def export_fusion_design(
    design: adsk.fusion.Design,
    export_dir: str,
    base_name: str,
    formats_to_export: list,
    target_ui_ref,
    format_settings=None,
):
    global logger
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
                refinement = (
                    format_settings.get("stl", {}).get(
                        "meshRefinement",
                        FORMAT_SETTINGS_DEFAULT.get("stl", {}).get("meshRefinement", "high"),
                    )
                )
                refinement = (refinement or "high").lower()
                refinement_map = {
                    "high": adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
                    "medium": adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
                    "low": adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
                }
                opts.meshRefinement = refinement_map.get(
                    refinement,
                    adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
                )
            elif fmt == "dwg" and hasattr(em, "createDWGExportOptions"):
                opts = em.createDWGExportOptions(path)
            elif fmt == "dxf" and hasattr(em, "createDXFExportOptions"):
                opts = em.createDXFExportOptions(path)
            else:
                if logger: logger.warning("Unsupported/unavailable export format: %s", fmt)
                continue

            if fmt in ("step", "stp") and opts:
                protocol = (
                    format_settings.get("step", {}).get("protocol", "AP214")
                )
                if hasattr(opts, "applicationProtocol"):
                    try:
                        opts.applicationProtocol = str(protocol)
                    except Exception:
                        if logger:
                            logger.debug(
                                "Failed to set STEP protocol to %s.",
                                protocol,
                                exc_info=True,
                            )

            if opts and em.execute(opts) and file_ok(path):
                exported.append(path)
                if logger: logger.info("Exported: %s (%d bytes)", path, os.path.getsize(path))
            else:
                target_ui_ref.messageBox(f"Export failed or empty file for {fmt}: {path}", CMD_NAME)
                if logger: logger.warning("Export failed/empty for %s -> %s", fmt, path)
        except Exception:
            if logger: logger.exception("Export error for %s", fmt)
            target_ui_ref.messageBox(f"Error exporting {fmt} for '{base_name}'", CMD_NAME)
    return exported


# -----------------------------
# UI: CommandCreated
# -----------------------------
class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        local_app_ref = app if app else adsk.core.Application.get()
        local_ui_ref = ui if ui else local_app_ref.userInterface

        try:
            config_cache = load_config()
            if not isinstance(config_cache, dict):
                config_cache = {}
            meta = config_cache.get(META_KEY, {})
            if not isinstance(meta, dict):
                meta = {}
                config_cache[META_KEY] = meta
            repo_names = sorted(
                name for name in config_cache.keys() if name != META_KEY
            )
            dropdown_items = (
                [ADD_NEW_OPTION] + repo_names if repo_names else [ADD_NEW_OPTION]
            )

            args.command.isAutoExecute = False
            args.command.isAutoTerminate = True
            inputs = args.command.commandInputs

            # Repo selector (grouped)
            repo_group = inputs.addGroupCommandInput("repoGroup", "Repository")
            repo_group.isExpanded = True
            repo_inputs = repo_group.children

            repoSelectorInput = repo_inputs.addDropDownCommandInput(
                "repoSelector", "Action / Select Repo",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )

            default_repo_name = None
            if repo_names:
                default_repo_name = (
                    meta.get("lastSelectedRepo") if isinstance(meta, dict) else None
                )
                if default_repo_name not in repo_names:
                    default_repo_name = repo_names[0]
            else:
                default_repo_name = ADD_NEW_OPTION

            for name_val in dropdown_items:
                is_selected = (name_val == default_repo_name)
                repoSelectorInput.listItems.add(name_val, is_selected, "")

            if (
                repoSelectorInput.selectedItem is None
                and repoSelectorInput.listItems.count
            ):
                repoSelectorInput.listItems.item(0).isSelected = True

            new_repo_name_input = repo_inputs.addStringValueInput(
                "newRepoName",
                "New Repo Name (if adding)",
                "",
            )
            git_url_input = repo_inputs.addStringValueInput(
                "gitUrl",
                "Git URL (if adding)",
                "https://github.com/user/repo.git",
            )
            repo_path_input = repo_inputs.addStringValueInput(
                "repoPath",
                "Repository Path",
                "",
            )
            browse_repo_button = repo_inputs.addBoolValueInput(
                "browseRepoPath", "Browse…", False, "", False
            )
            browse_repo_button.isFullWidth = False
            repo_status_input = repo_inputs.addTextBoxCommandInput(
                "repoValidationStatus", "", "", 2, True
            )
            repo_status_input.isFullWidth = True
            git_status_input = repo_inputs.addTextBoxCommandInput(
                "gitValidationStatus", "", "", 2, True
            )
            git_status_input.isFullWidth = True

            def update_new_repo_visibility(selection_name: str):
                show_new_repo = (selection_name == ADD_NEW_OPTION)
                new_repo_name_input.isVisible = show_new_repo
                git_url_input.isVisible = show_new_repo
                git_status_input.isVisible = show_new_repo

            current_selection_name = (
                repoSelectorInput.selectedItem.name
                if repoSelectorInput.selectedItem
                else ADD_NEW_OPTION
            )
            update_new_repo_visibility(current_selection_name)

            # Export formats (checkbox dropdown)
            export_group = inputs.addGroupCommandInput(
                "exportGroup", "Export Options"
            )
            export_group.isExpanded = True
            export_inputs = export_group.children

            available_formats = [
                "f3d",
                "step",
                "iges",
                "sat",
                "stl",
                "dwg",
                "dxf",
            ]
            default_formats_list = ["f3d", "step", "stl"]
            exportFormatsDropdown = export_inputs.addDropDownCommandInput(
                "exportFormatsConfig", "Export Formats (config)",
                adsk.core.DropDownStyles.CheckBoxDropDownStyle
            )
            for fmt in available_formats:
                exportFormatsDropdown.listItems.add(
                    fmt, fmt in default_formats_list, ""
                )

            format_settings_state = {}
            format_setting_inputs = {}
            
            # Try to get the appropriate table presentation style with fallbacks
            try:
                table_style = getattr(adsk.core.TablePresentationStyles, 'minimalTablePresentationStyle', None)
                if table_style is None:
                    # Try alternative name suggested by the error
                    table_style = getattr(adsk.core.TablePresentationStyles, 'nameValueTablePresentationStyle', None)
                if table_style is None:
                    # If still None, try to get any available style
                    style_names = ['defaultTablePresentationStyle', 'standardTablePresentationStyle']
                    for style_name in style_names:
                        table_style = getattr(adsk.core.TablePresentationStyles, style_name, None)
                        if table_style is not None:
                            break
                
                # Final fallback - create table without specifying style
                if table_style is not None:
                    format_settings_table = export_inputs.addTableCommandInput(
                        "formatSettingsTable", "Format Settings", 2, table_style
                    )
                else:
                    # Create table with minimal parameters
                    format_settings_table = export_inputs.addTableCommandInput(
                        "formatSettingsTable", "Format Settings", 2
                    )
                    
            except Exception as e:
                logger.warning(f"Could not create format settings table with presentation style: {e}")
                # Fallback to basic table creation
                format_settings_table = export_inputs.addTableCommandInput(
                    "formatSettingsTable", "Format Settings", 2
                )
            
            format_settings_table.maximumVisibleRows = len(available_formats) + 1
            format_settings_table.columnSpacing = 4
            format_settings_table.rowSpacing = 2

            def get_selected_formats():
                return [
                    item.name
                    for item in exportFormatsDropdown.listItems
                    if item.isSelected
                ]

            def ensure_format_defaults(fmt: str):
                defaults = FORMAT_SETTINGS_DEFAULT.get(fmt, {})
                fmt_state = format_settings_state.setdefault(fmt, {})
                for key, value in defaults.items():
                    fmt_state.setdefault(key, value)

            def sync_format_settings_rows():
                format_settings_table.clear()
                format_setting_inputs.clear()

                header_label = export_inputs.addTextBoxCommandInput(
                    "formatSettingsHeaderLabel", "", "Format", 1, True
                )
                header_label.isFullWidth = True
                header_setting = export_inputs.addTextBoxCommandInput(
                    "formatSettingsHeaderSetting", "", "Setting", 1, True
                )
                header_setting.isFullWidth = True
                format_settings_table.addCommandInput(header_label, 0, 0)
                format_settings_table.addCommandInput(header_setting, 0, 1)

                row_index = 1
                for fmt in get_selected_formats():
                    ensure_format_defaults(fmt)
                    label = export_inputs.addTextBoxCommandInput(
                        f"formatSettingsLabel_{fmt}", "", fmt.upper(), 1, True
                    )
                    label.isFullWidth = True
                    dropdown = export_inputs.addDropDownCommandInput(
                        f"formatSetting_{fmt}", "",
                        adsk.core.DropDownStyles.TextListDropDownStyle
                    )

                    options = FORMAT_SETTINGS_OPTIONS.get(fmt, [])
                    dropdown.listItems.clear()
                    current_state = format_settings_state.get(fmt, {})
                    state_key = list(FORMAT_SETTINGS_DEFAULT.get(fmt, {}).keys() or ["value"])[0]
                    current_value = current_state.get(
                        state_key,
                        FORMAT_SETTINGS_DEFAULT.get(fmt, {}).get(state_key, "default")
                    )
                    for label_text, value in options:
                        dropdown.listItems.add(
                            label_text,
                            value == current_value,
                            ""
                        )
                    format_setting_inputs[fmt] = (dropdown, state_key, options)
                    format_settings_table.addCommandInput(label, row_index, 0)
                    format_settings_table.addCommandInput(dropdown, row_index, 1)
                    row_index += 1

            def collect_format_settings_from_ui():
                result = {}
                for fmt, data in format_setting_inputs.items():
                    dropdown, state_key, options = data
                    selected_item = dropdown.selectedItem
                    if not selected_item:
                        continue
                    selected_label = selected_item.name
                    value_lookup = dict(options)
                    selected_value = value_lookup.get(selected_label, selected_label)
                    result[fmt] = {state_key: selected_value}
                return result

            sync_format_settings_rows()

            def compute_branch_preview(branch_template: str) -> str:
                design_preview = get_fusion_design()
                if design_preview and isinstance(design_preview, adsk.fusion.Design):
                    base_name_preview = _safe_base(design_preview.rootComponent.name)
                else:
                    base_name_preview = "Design"
                generated_branch, _ = generate_branch_name(branch_template, base_name_preview)
                return generated_branch

            def update_export_subfolder_feedback(raw_value: str):
                try:
                    normalized = normalize_export_subfolder(raw_value)
                    if normalized:
                        flow_status_input.text = f"✅ Exports will be copied to repo/{normalized}"
                    else:
                        flow_status_input.text = ""
                    return normalized
                except ValueError as exc:
                    flow_status_input.text = f"❌ {exc}"
                    return raw_value

            # Templates and per-push message
            git_group = inputs.addGroupCommandInput("gitGroup", "Git Settings")
            git_group.isExpanded = True
            git_inputs = git_group.children

            git_inputs.addStringValueInput(
                "defaultMessageConfig",
                "Default Commit Template (config)",
                "Design update: {filename}",
            )
            git_inputs.addStringValueInput(
                "branchFormatConfig",
                "Branch Format (config)",
                "fusion-export/{filename}-{timestamp}",
            )

            last_commit_message = "Updated design"
            if isinstance(meta, dict):
                last_commit_message = meta.get("lastCommitMessage", last_commit_message)
            git_inputs.addStringValueInput(
                "commitMsgPush",
                "Commit Message (for this push)",
                last_commit_message,
            )

            flow_group = inputs.addGroupCommandInput("flowGroup", "Git Flow Helpers")
            flow_group.isExpanded = True
            flow_inputs = flow_group.children

            flow_inputs.addStringValueInput(
                "exportSubfolder",
                "Export Subfolder (optional)",
                "",
            )
            flow_inputs.addStringValueInput(
                "branchPreview",
                "Branch Name (for this push)",
                "",
            )
            skip_pull_input = flow_inputs.addBoolValueInput(
                "skipPull",
                "Skip pull (force push)",
                True,
                "",
                False,
            )
            skip_pull_input.isFullWidth = False

            use_pat_input = flow_inputs.addBoolValueInput(
                "useStoredPat",
                "Use stored PAT (Windows only)",
                True,
                "",
                False,
            )
            use_pat_input.isFullWidth = False
            use_pat_input.isVisible = IS_WINDOWS

            manage_pat_button = flow_inputs.addBoolValueInput(
                "managePat",
                "Manage Personal Access Token…",
                False,
                "",
                False,
            )
            manage_pat_button.isFullWidth = True
            manage_pat_button.isVisible = IS_WINDOWS

            flow_status_input = flow_inputs.addTextBoxCommandInput(
                "flowValidationStatus",
                "",
                "",
                2,
                True,
            )
            flow_status_input.isFullWidth = True

            log_group = inputs.addGroupCommandInput("logGroup", "Observability")
            log_group.isExpanded = True
            log_inputs = log_group.children

            logLevelDropdown = log_inputs.addDropDownCommandInput(
                "logLevel",
                "Log Level",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            for level_name in ["ERROR", "WARNING", "INFO", "DEBUG"]:
                logLevelDropdown.listItems.add(level_name, level_name == current_log_level_name, "")

            open_log_button = log_inputs.addBoolValueInput(
                "openLogFile",
                "Open Log File…",
                False,
                "",
                False,
            )
            open_log_button.isFullWidth = True

            # Apply saved settings for selected repo
            def apply_repo_settings(repo_name: str):
                det = config_cache.get(repo_name, {})
                saved_formats = set(det.get("exportFormats", []))
                for item in exportFormatsDropdown.listItems:
                    is_saved = item.name in saved_formats if saved_formats else False
                    item.isSelected = (
                        is_saved
                        or (
                            not saved_formats
                            and item.name in default_formats_list
                        )
                    )

                format_settings_state.clear()
                saved_settings = det.get("formatSettings", {})
                if isinstance(saved_settings, dict):
                    format_settings_state.update(saved_settings)
                sync_format_settings_rows()

                inputs.itemById("defaultMessageConfig").value = det.get(
                    "defaultMessage",
                    "Design update: {filename}",
                )
                inputs.itemById("branchFormatConfig").value = det.get(
                    "branchFormat",
                    "fusion-export/{filename}-{timestamp}",
                )
                repo_path_input.value = det.get("path", "")
                git_url_input.value = det.get("url", "")

                export_subfolder_value = det.get("exportSubfolder", "")
                export_input = inputs.itemById("exportSubfolder")
                if export_input:
                    export_input.value = export_subfolder_value

                skip_pull_input.value = bool(det.get("skipPullDefault", False))
                if IS_WINDOWS:
                    use_pat_input.value = bool(det.get("useStoredPat", False))

                repo_log_level = det.get("logLevel") or meta.get("globalLogLevel") or current_log_level_name
                for item in logLevelDropdown.listItems:
                    item.isSelected = (item.name == repo_log_level)

                branch_format_current = inputs.itemById("branchFormatConfig").value
                generated_branch = compute_branch_preview(branch_format_current)
                branch_preview_input = inputs.itemById("branchPreview")
                if branch_preview_input:
                    branch_preview_input.value = det.get("lastBranchPreview", generated_branch)
                update_export_subfolder_feedback(export_subfolder_value)

            sel_item = repoSelectorInput.selectedItem
            if sel_item and sel_item.name != ADD_NEW_OPTION:
                apply_repo_settings(sel_item.name)

            auto_path_state = {"auto": True}

            def default_path_for_new_repo() -> str:
                proposed_name = new_repo_name_input.value.strip()
                if not proposed_name:
                    return os.path.join(REPO_BASE_DIR, "NewRepo")
                sanitized = _safe_base(proposed_name) or proposed_name
                return os.path.join(REPO_BASE_DIR, sanitized)

            def validate_repo_inputs(selection_name: str, raw_path: str, git_url_val: str):
                messages = {"path": ("", "info"), "git": ("", "info")}
                ok = True

                def set_msg(field: str, text: str, severity: str = "info"):
                    messages[field] = (text, severity)

                expanded = raw_path.strip()
                if expanded:
                    expanded = os.path.expanduser(expanded)
                normalized_path = os.path.abspath(expanded) if expanded else ""

                git_dir_exists = os.path.isdir(os.path.join(normalized_path, ".git"))
                has_git_url = bool(git_url_val.strip())

                if not normalized_path:
                    set_msg("path", "⚠️ Provide a repository path.", "error")
                    ok = False
                elif not os.path.isabs(normalized_path):
                    set_msg("path", "⚠️ Path must be absolute.", "error")
                    ok = False
                elif not os.path.exists(normalized_path):
                    if selection_name == ADD_NEW_OPTION and has_git_url:
                        set_msg(
                            "path",
                            "ℹ️ Path will be created when cloning the remote repository.",
                            "info",
                        )
                    else:
                        set_msg("path", "❌ Path does not exist.", "error")
                        ok = False
                elif not os.path.isdir(normalized_path):
                    set_msg("path", "❌ Path is not a directory.", "error")
                    ok = False
                else:
                    if git_dir_exists:
                        set_msg("path", "✅ Repository path looks good.", "success")
                    elif selection_name == ADD_NEW_OPTION and has_git_url:
                        set_msg(
                            "path",
                            "ℹ️ .git will be created after cloning the remote repo.",
                            "info",
                        )
                    else:
                        set_msg(
                            "path",
                            "❌ Missing .git directory at this path.",
                            "error",
                        )
                        ok = False

                if selection_name == ADD_NEW_OPTION:
                    if has_git_url:
                        pattern = r"^(https://|git@|ssh://).+\\.git$"
                        if re.match(pattern, git_url_val.strip()):
                            set_msg("git", "✅ Git URL format looks valid.", "success")
                        else:
                            set_msg(
                                "git",
                                "❌ Git URL should be HTTPS, SSH, or git@ and end with .git.",
                                "error",
                            )
                            ok = False
                    else:
                        if git_dir_exists:
                            set_msg(
                                "git",
                                "✅ Local repository detected (no remote URL provided).",
                                "success",
                            )
                        else:
                            set_msg(
                                "git",
                                "⚠️ Provide a Git URL or choose a folder that already contains a .git directory.",
                                "error",
                            )
                            ok = False
                else:
                    set_msg("git", "", "info")

                return {
                    "messages": messages,
                    "ok": ok,
                    "path": normalized_path,
                    "has_git_dir": git_dir_exists,
                }

            def update_validation(selection_name: str = None):
                selected = selection_name
                if not selected:
                    sel = repoSelectorInput.selectedItem
                    selected = sel.name if sel else ADD_NEW_OPTION

                validation = validate_repo_inputs(
                    selected,
                    repo_path_input.value,
                    git_url_input.value if selected == ADD_NEW_OPTION else ""
                )
                repo_status_input.text = validation["messages"]["path"][0]
                if selected == ADD_NEW_OPTION:
                    git_status_input.text = validation["messages"]["git"][0]
                else:
                    git_status_input.text = ""
                return validation

            def ensure_new_repo_defaults():
                if repoSelectorInput.selectedItem and repoSelectorInput.selectedItem.name == ADD_NEW_OPTION:
                    if auto_path_state.get("auto", True):
                        repo_path_input.value = default_path_for_new_repo()
                    format_settings_state.clear()
                    sync_format_settings_rows()
                    export_input = inputs.itemById("exportSubfolder")
                    if export_input:
                        export_input.value = ""
                    skip_pull_input.value = False
                    if IS_WINDOWS:
                        use_pat_input.value = False
                    branch_template_default = inputs.itemById("branchFormatConfig").value
                    branch_preview_input = inputs.itemById("branchPreview")
                    if branch_preview_input:
                        branch_preview_input.value = compute_branch_preview(branch_template_default)
                    flow_status_input.text = ""
                    for item in logLevelDropdown.listItems:
                        item.isSelected = (item.name == (meta.get("globalLogLevel") or current_log_level_name))
                update_validation()

            def get_selected_repo_name() -> str:
                sel = repoSelectorInput.selectedItem
                return sel.name if sel else ADD_NEW_OPTION

            def prompt_pat_credentials(existing_username: str = "") -> Optional[dict]:
                if not IS_WINDOWS:
                    return None
                username_value, cancelled = local_ui_ref.inputBox(
                    "Enter the username associated with the PAT (leave blank to rely on token only):",
                    CMD_NAME,
                    existing_username or "",
                )
                if cancelled:
                    return None
                token_value, token_cancelled = local_ui_ref.inputBox(
                    "Enter the Personal Access Token (input is visible):",
                    CMD_NAME,
                    "",
                )
                if token_cancelled:
                    return None
                token_value = token_value.strip()
                if not token_value:
                    local_ui_ref.messageBox("Token cannot be empty.", CMD_NAME)
                    return None
                return {"username": username_value.strip(), "token": token_value}

            def manage_pat_for_repo(repo_name: str):
                if not IS_WINDOWS:
                    local_ui_ref.messageBox("PAT storage is only available on Windows.", CMD_NAME)
                    return

                existing = read_stored_pat(repo_name)
                if existing:
                    choice = local_ui_ref.messageBox(
                        "A stored PAT already exists for this repository.\n\nYes: Update token\nNo: Delete token\nCancel: Leave unchanged",
                        CMD_NAME,
                        adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
                    )
                    if choice == adsk.core.DialogResults.DialogYes:
                        creds = prompt_pat_credentials(existing.get("username", ""))
                        if creds:
                            store_pat(repo_name, creds["username"], creds["token"])
                            local_ui_ref.messageBox("Personal Access Token updated.", CMD_NAME)
                            use_pat_input.value = True
                    elif choice == adsk.core.DialogResults.DialogNo:
                        delete_pat(repo_name)
                        local_ui_ref.messageBox("Stored Personal Access Token removed.", CMD_NAME)
                        use_pat_input.value = False
                    return

                add_choice = local_ui_ref.messageBox(
                    "No stored PAT found for this repository. Would you like to add one now?",
                    CMD_NAME,
                    adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                )
                if add_choice == adsk.core.DialogResults.DialogYes:
                    creds = prompt_pat_credentials()
                    if creds:
                        store_pat(repo_name, creds["username"], creds["token"])
                        local_ui_ref.messageBox("Personal Access Token saved.", CMD_NAME)
                        use_pat_input.value = True

            class InputChangedHandler(adsk.core.InputChangedEventHandler):
                def __init__(self, repoSelector):
                    super().__init__()
                    self._repoSelector = repoSelector
                def notify(self, ic_args: adsk.core.InputChangedEventArgs):
                    if not ic_args.input:
                        return

                    input_id = ic_args.input.id
                    if input_id == "repoSelector":
                        sel = self._repoSelector.selectedItem
                        if sel:
                            update_new_repo_visibility(sel.name)
                            if sel.name == ADD_NEW_OPTION:
                                auto_path_state["auto"] = True
                                ensure_new_repo_defaults()
                            else:
                                apply_repo_settings(sel.name)
                                auto_path_state["auto"] = False
                                update_validation(sel.name)
                    elif input_id == "newRepoName":
                        auto_path_state["auto"] = True
                        ensure_new_repo_defaults()
                    elif input_id == "repoPath":
                        auto_path_state["auto"] = False
                        update_validation()
                    elif input_id == "gitUrl":
                        update_validation()
                    elif input_id == "exportFormatsConfig":
                        sync_format_settings_rows()
                    elif input_id == "branchFormatConfig":
                        template_value = inputs.itemById("branchFormatConfig").value
                        branch_preview_input = inputs.itemById("branchPreview")
                        if branch_preview_input:
                            branch_preview_input.value = compute_branch_preview(template_value)
                    elif input_id == "branchPreview":
                        preview_input = inputs.itemById("branchPreview")
                        if preview_input:
                            sanitized = sanitize_branch_name(preview_input.value)
                            if sanitized != preview_input.value:
                                preview_input.value = sanitized
                    elif input_id == "exportSubfolder":
                        export_input = inputs.itemById("exportSubfolder")
                        if export_input:
                            normalized_value = update_export_subfolder_feedback(export_input.value)
                            if normalized_value != export_input.value:
                                export_input.value = normalized_value
                    elif input_id.startswith("formatSetting_"):
                        fmt_key = input_id.split("_", 1)[1]
                        data = format_setting_inputs.get(fmt_key)
                        if data:
                            dropdown, state_key, options = data
                            selected = dropdown.selectedItem
                            if selected:
                                lookup = dict(options)
                                format_settings_state.setdefault(fmt_key, {})[state_key] = lookup.get(
                                    selected.name,
                                    selected.name,
                                )
                    elif input_id == "browseRepoPath":
                        ic_args.input.value = False
                        folder_dialog = local_ui_ref.createFolderDialog()
                        folder_dialog.title = "Select Repository Folder"
                        if folder_dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                            repo_path_input.value = folder_dialog.folder
                            auto_path_state["auto"] = False
                        update_validation()
                    elif input_id == "logLevel":
                        selected_item = logLevelDropdown.selectedItem
                        if selected_item:
                            set_logger_level(selected_item.name)
                    elif input_id == "openLogFile":
                        ic_args.input.value = False
                        open_log_file(local_ui_ref)
                    elif input_id == "managePat":
                        ic_args.input.value = False
                        repo_name_for_pat = get_selected_repo_name()
                        if repo_name_for_pat == ADD_NEW_OPTION:
                            local_ui_ref.messageBox("Add the repository before managing credentials.", CMD_NAME)
                        else:
                            manage_pat_for_repo(repo_name_for_pat)
                    elif input_id == "useStoredPat" and IS_WINDOWS:
                        repo_name_for_pat = get_selected_repo_name()
                        if repo_name_for_pat == ADD_NEW_OPTION:
                            local_ui_ref.messageBox("Add the repository before enabling stored PAT usage.", CMD_NAME)
                            use_pat_input.value = False
                        elif use_pat_input.value and not read_stored_pat(repo_name_for_pat):
                            local_ui_ref.messageBox(
                                "No stored Personal Access Token was found. Use 'Manage Personal Access Token…' to add one first.",
                                CMD_NAME,
                            )
                            use_pat_input.value = False

            on_input_changed = InputChangedHandler(repoSelectorInput)
            args.command.inputChanged.add(on_input_changed)
            handlers.append(on_input_changed)

            ensure_new_repo_defaults()

            # Execute handler
            class ExecuteHandler(adsk.core.CommandEventHandler):
                def notify(self, execute_args: adsk.core.CommandEventArgs):
                    nonlocal config_cache, meta
                    global logger
                    current_app_ref = app if app else adsk.core.Application.get()
                    current_ui_ref = ui if ui else current_app_ref.userInterface
                    progress = None
                    temp_dir = None
                    try:
                        cmd_inputs = execute_args.command.commandInputs
                        selected_action_item = cmd_inputs.itemById("repoSelector").selectedItem
                        if not selected_action_item:
                            current_ui_ref.messageBox("No action or repository selected.")
                            return
                        selected_action = selected_action_item.name
                        current_config = config_cache
                        meta_section = current_config.setdefault(META_KEY, {})
                        if not isinstance(meta_section, dict):
                            meta_section = {}
                            current_config[META_KEY] = meta_section
                        meta = meta_section

                        repo_path_raw = cmd_inputs.itemById("repoPath").value.strip()
                        git_url_val = ""
                        if selected_action == ADD_NEW_OPTION:
                            git_url_val = cmd_inputs.itemById("gitUrl").value.strip()

                        validation = validate_repo_inputs(
                            selected_action,
                            repo_path_raw,
                            git_url_val,
                        )
                        if not validation["ok"]:
                            error_lines = [
                                msg
                                for msg, severity in validation["messages"].values()
                                if severity == "error"
                            ]
                            if error_lines:
                                current_ui_ref.messageBox(
                                    "Please fix the following issues before continuing:\n\n"
                                    + "\n".join(error_lines),
                                    CMD_NAME,
                                )
                                return
                        normalized_repo_path = validation["path"]
                        if normalized_repo_path:
                            repo_path_input.value = normalized_repo_path
                        has_git_dir = validation["has_git_dir"]

                        # Formats
                        export_formats_input = cmd_inputs.itemById("exportFormatsConfig")
                        selected_formats = [item.name for item in export_formats_input.listItems if item.isSelected]
                        export_formats_val = selected_formats if selected_formats else ["f3d"]
                        current_format_settings = collect_format_settings_from_ui()
                        current_format_settings = {
                            fmt: current_format_settings.get(fmt)
                            for fmt in export_formats_val
                            if current_format_settings.get(fmt)
                        }

                        # Templates
                        default_message_tpl_val = cmd_inputs.itemById("defaultMessageConfig").value.strip() or "Design update: {filename}"
                        branch_format_tpl_val = cmd_inputs.itemById("branchFormatConfig").value.strip() or "fusion-export/{filename}-{timestamp}"

                        # ADD NEW
                        if selected_action == ADD_NEW_OPTION:
                            repo_name_to_add = cmd_inputs.itemById("newRepoName").value.strip()
                            git_url = git_url_val
                            if not repo_name_to_add:
                                current_ui_ref.messageBox(
                                    "New repository name cannot be empty.",
                                    CMD_NAME,
                                )
                                return
                            if repo_name_to_add == META_KEY:
                                current_ui_ref.messageBox(
                                    "Repository name is reserved for internal use.",
                                    CMD_NAME,
                                )
                                return
                            if repo_name_to_add in current_config:
                                current_ui_ref.messageBox(
                                    f"Repo '{repo_name_to_add}' already exists.",
                                    CMD_NAME,
                                )
                                return

                            local_path = normalized_repo_path or os.path.join(REPO_BASE_DIR, repo_name_to_add)
                            parent_dir = os.path.dirname(local_path)
                            if parent_dir and not os.path.exists(parent_dir):
                                os.makedirs(parent_dir, exist_ok=True)

                            progress = None
                            if git_url:
                                progress = current_ui_ref.createProgressDialog()
                                progress.isBackgroundTranslucencyEnabled = True
                                progress.cancelButtonText = ""
                                progress.show(
                                    "Clone Repository",
                                    "Cloning repository…",
                                    0,
                                    1,
                                    0,
                                )

                                if os.path.exists(local_path):
                                    confirm = current_ui_ref.messageBox(
                                        f"Local path '{local_path}' exists.\nUse existing or cancel?",
                                        CMD_NAME,
                                        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                                    )
                                    if confirm == adsk.core.DialogResults.DialogNo:
                                        progress.hide()
                                        return
                                else:
                                    try:
                                        _git(
                                            os.path.dirname(local_path),
                                            "clone",
                                            git_url,
                                            local_path,
                                        )
                                    except Exception as e:
                                        progress.hide()
                                        err_msg_clone = f"Failed to clone repo:\n{str(e)}"
                                        current_ui_ref.messageBox(err_msg_clone, CMD_NAME)
                                        if logger:
                                            logger.error(err_msg_clone)
                                        return

                                if progress:
                                    progress.hide()
                            else:
                                if not has_git_dir:
                                    current_ui_ref.messageBox(
                                        "Selected folder does not contain a .git directory.",
                                        CMD_NAME,
                                    )
                                    return

                            current_config[repo_name_to_add] = {
                                "url": git_url,
                                "path": local_path.replace("/", os.sep),
                                "exportFormats": export_formats_val,
                                "formatSettings": current_format_settings,
                                "defaultMessage": default_message_tpl_val,
                                "branchFormat": branch_format_tpl_val
                            }
                            if isinstance(meta_section, dict):
                                meta_section["lastSelectedRepo"] = repo_name_to_add
                                meta_section.setdefault("lastCommitMessage", "Updated design")
                            save_config(current_config)
                            current_ui_ref.messageBox(
                                f"Repository '{repo_name_to_add}' added. Restart the command to select it for push.",
                                CMD_NAME
                            )
                            if logger: logger.info("Repository '%s' added (%s).", repo_name_to_add, git_url)
                            return

                        # EXISTING → PUSH
                        selected_repo_name = selected_action
                        if selected_repo_name not in current_config:
                            msg_repo_not_found = f"Error: Selected repo '{selected_repo_name}' not found in config."
                            current_ui_ref.messageBox(msg_repo_not_found, CMD_NAME)
                            if logger: logger.error(msg_repo_not_found)
                            return

                        selected_repo_details = current_config[selected_repo_name]
                        selected_repo_details["path"] = normalized_repo_path or selected_repo_details.get("path", "")
                        selected_repo_details["exportFormats"] = export_formats_val
                        selected_repo_details["formatSettings"] = current_format_settings
                        selected_repo_details["defaultMessage"] = default_message_tpl_val
                        selected_repo_details["branchFormat"] = branch_format_tpl_val

                        commit_msg_input_value = cmd_inputs.itemById("commitMsgPush").value.strip()
                        commit_msg_for_this_push = commit_msg_input_value or selected_repo_details["defaultMessage"]
                        branch_format_for_this_push = selected_repo_details.get("branchFormat", "fusion-export/{filename}-{timestamp}")

                        export_subfolder_input = cmd_inputs.itemById("exportSubfolder")
                        export_subfolder_raw = export_subfolder_input.value if export_subfolder_input else ""
                        try:
                            normalized_export_subfolder = normalize_export_subfolder(export_subfolder_raw)
                        except ValueError as exc:
                            current_ui_ref.messageBox(str(exc), CMD_NAME)
                            return

                        skip_pull_selected = bool(cmd_inputs.itemById("skipPull").value)

                        branch_preview_input = cmd_inputs.itemById("branchPreview")
                        branch_override_raw = branch_preview_input.value.strip() if branch_preview_input else ""
                        branch_override_sanitized = sanitize_branch_name(branch_override_raw) if branch_override_raw else ""
                        if branch_override_raw and not branch_override_sanitized:
                            current_ui_ref.messageBox(
                                "Branch name contains unsupported characters even after sanitization.",
                                CMD_NAME,
                            )
                            return
                        if branch_preview_input and branch_override_sanitized:
                            branch_preview_input.value = branch_override_sanitized

                        use_pat_selected = False
                        if IS_WINDOWS:
                            use_pat_input_cmd = cmd_inputs.itemById("useStoredPat")
                            use_pat_selected = bool(use_pat_input_cmd.value) if use_pat_input_cmd else False

                        selected_log_item = logLevelDropdown.selectedItem or next(
                            (item for item in logLevelDropdown.listItems if item.isSelected),
                            None,
                        )
                        log_level_name = selected_log_item.name if selected_log_item else current_log_level_name
                        set_logger_level(log_level_name)

                        selected_repo_details["exportSubfolder"] = normalized_export_subfolder
                        selected_repo_details["skipPullDefault"] = skip_pull_selected
                        selected_repo_details["logLevel"] = log_level_name
                        if IS_WINDOWS:
                            selected_repo_details["useStoredPat"] = use_pat_selected
                        if branch_override_sanitized:
                            selected_repo_details["lastBranchPreview"] = branch_override_sanitized
                        else:
                            selected_repo_details["lastBranchPreview"] = compute_branch_preview(branch_format_for_this_push)

                        if isinstance(meta_section, dict):
                            meta_section["lastSelectedRepo"] = selected_repo_name
                            meta_section["lastCommitMessage"] = commit_msg_for_this_push
                            meta_section["globalLogLevel"] = log_level_name

                        current_config[selected_repo_name] = selected_repo_details
                        save_config(current_config)

                        pat_credentials = None
                        if IS_WINDOWS and use_pat_selected:
                            pat_credentials = read_stored_pat(selected_repo_name)
                            if not pat_credentials:
                                current_ui_ref.messageBox(
                                    "No stored Personal Access Token was found. Use 'Manage Personal Access Token…' before enabling this option.",
                                    CMD_NAME,
                                )
                                return

                        if not check_git_available(current_ui_ref):
                            return
                        design = get_fusion_design()
                        if not design:
                            current_ui_ref.messageBox("No active Fusion design.", CMD_NAME)
                            return

                        raw_name = design.rootComponent.name
                        base_name = _safe_base(raw_name)

                        git_repo_path = os.path.expanduser(selected_repo_details["path"]).replace("/", os.sep)
                        if not os.path.isdir(os.path.join(git_repo_path, ".git")):
                            current_ui_ref.messageBox(
                                f"Path '{git_repo_path}' for repo '{selected_repo_name}' is not a Git repo.", CMD_NAME
                            )
                            return

                        progress = current_ui_ref.createProgressDialog()
                        progress.isBackgroundTranslucencyEnabled = True
                        progress.cancelButtonText = ""
                        progress.show("Fusion → GitHub", "Exporting design…", 0, 2, 0)

                        final_abs = []
                        export_warnings = []
                        exported_display_names = []
                        destination_root = ensure_export_subfolder_exists(git_repo_path, normalized_export_subfolder)
                        with temporary_export_dir(git_repo_path) as temp_dir:
                            formats_for_this_push = selected_repo_details.get("exportFormats", ["f3d"])
                            format_settings_for_push = selected_repo_details.get("formatSettings", {})
                            valid_formats, detected_warnings = determine_valid_export_formats(
                                design,
                                formats_for_this_push,
                            )
                            export_warnings.extend(detected_warnings)
                            if not valid_formats:
                                progress.hide()
                                current_ui_ref.messageBox(
                                    "No valid export formats available for this design.",
                                    CMD_NAME,
                                )
                                return

                            format_settings_for_push = {
                                fmt: format_settings_for_push.get(fmt, {})
                                for fmt in valid_formats
                            }
                            exported_files_paths = export_fusion_design(
                                design,
                                temp_dir,
                                base_name,
                                valid_formats,
                                current_ui_ref,
                                format_settings_for_push,
                            )
                            if not exported_files_paths:
                                progress.hide()
                                current_ui_ref.messageBox(
                                    "No files exported. Aborting.",
                                    CMD_NAME,
                                )
                                return

                            # Copy into repo (respecting subfolder); collect ABS DEST PATHS
                            for src in exported_files_paths:
                                fname = os.path.basename(src)
                                dst = os.path.join(destination_root, fname)
                                try:
                                    shutil.copy2(src, dst)
                                except Exception as e:
                                    progress.hide()
                                    current_ui_ref.messageBox(
                                        f"Copy failed:\nSRC: {src}\nDST: {dst}\n{e}",
                                        CMD_NAME,
                                    )
                                    if logger:
                                        logger.error(
                                            "Copy failed %s -> %s : %s",
                                            src,
                                            dst,
                                            e,
                                            exc_info=True,
                                        )
                                    return
                                if not os.path.exists(dst) or os.path.getsize(dst) == 0:
                                    progress.hide()
                                    current_ui_ref.messageBox(
                                        f"Copied file missing/empty:\n{dst}",
                                        CMD_NAME,
                                    )
                                    if logger:
                                        logger.error(
                                            "Copied file missing/empty: %s",
                                            dst,
                                        )
                                    return
                                final_abs.append(os.path.normpath(dst))
                                rel_display = os.path.relpath(dst, git_repo_path).replace("\\", "/")
                                exported_display_names.append(rel_display)
                                if logger:
                                    logger.info(
                                        "Copied -> %s (%d bytes)",
                                        dst,
                                        os.path.getsize(dst),
                                    )

                        if progress:
                            progress.message = "Pushing to GitHub…"
                            progress.progressValue = 1

                        git_ui_adapter = FusionCommandGitUI(current_ui_ref)
                        git_result = core_handle_git_operations(
                            git_repo_path,
                            final_abs,
                            commit_msg_for_this_push,
                            branch_format_for_this_push,
                            git_ui_adapter,
                            base_name,
                            branch_override=branch_override_sanitized or None,
                            skip_pull=skip_pull_selected,
                            pat_credentials=pat_credentials,
                            logger=logger,
                        )

                        if progress:
                            progress.progressValue = 2
                            progress.hide()

                        if git_result:
                            branch_name_effective = git_result.get("branch", "<unknown>")
                            summary_lines = [
                                f"✅ Push successful to branch: {branch_name_effective}",
                                f"Settings for '{selected_repo_name}' updated.",
                            ]
                            if exported_display_names:
                                summary_lines.append("")
                                summary_lines.append("Exported files:")
                                summary_lines.extend(
                                    f" • {name}"
                                    for name in exported_display_names
                                )
                            status_notes = []
                            if git_result.get("stashed"):
                                status_notes.append("Auto-stashed local changes and restored them afterward.")
                            if git_result.get("force_push"):
                                status_notes.append("Used --force-with-lease (skip pull).")
                            if git_result.get("pull_failed"):
                                status_notes.append("Initial pull --rebase failed; branch was force-pushed.")
                            if status_notes:
                                summary_lines.append("")
                                summary_lines.append("Git flow details:")
                                summary_lines.extend(f" • {note}" for note in status_notes)
                            if export_warnings:
                                summary_lines.append("")
                                summary_lines.append("Warnings:")
                                summary_lines.extend(
                                    f" • {warning}"
                                    for warning in export_warnings
                                )
                            current_ui_ref.messageBox(
                                "\n".join(summary_lines),
                                CMD_NAME,
                            )
                        else:
                            failure_lines = [
                                "Git operations completed with issues or were aborted.",
                            ]
                            if export_warnings:
                                failure_lines.append("")
                                failure_lines.append("Warnings:")
                                failure_lines.extend(
                                    f" • {warning}"
                                    for warning in export_warnings
                                )
                            current_ui_ref.messageBox(
                                "\n".join(failure_lines),
                                CMD_NAME,
                            )

                    except Exception:
                        error_message = 'ExecuteHandler failed:\n{}'.format(traceback.format_exc())
                        if current_ui_ref: current_ui_ref.messageBox(error_message, CMD_NAME)
                        if logger: logger.exception("ExecuteHandler failed")
                    finally:
                        try:
                            if progress: progress.hide()
                        except: pass
                        try:
                            if temp_dir and os.path.exists(temp_dir):
                                shutil.rmtree(temp_dir)
                        except Exception:
                            if logger: logger.warning("Failed to cleanup temp_dir: %s", temp_dir, exc_info=True)

            on_execute = ExecuteHandler()
            args.command.execute.add(on_execute)
            handlers.append(on_execute)

        except Exception:
            error_message = 'GitCommandCreatedEventHandler failed:\n{}'.format(traceback.format_exc())
            final_ui_ref = local_ui_ref if local_ui_ref else ui
            if final_ui_ref: final_ui_ref.messageBox(error_message, CMD_NAME)
            if logger: logger.exception("GitCommandCreatedEventHandler failed")

# -----------------------------
# Lifecycle
# -----------------------------
def run(context):
    global push_cmd_def, git_push_control, handlers, app, ui, logger, is_initialized

    if not app or not ui:
        try:
            temp_app_run = adsk.core.Application.get()
            if temp_app_run:
                app = temp_app_run
                ui = temp_app_run.userInterface
            if not ui:
                print("CRITICAL: Could not obtain UserInterface in run().")
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in run(): {traceback.format_exc()}")
            return

    if is_initialized:
        if logger: logger.info("Add-in already initialized; skipping toolbar injection.")
        adsk.autoTerminate(False)
        return

    try:
        setup_logger()
    except Exception:
        msg_log_fail = f"CRITICAL: Failed to setup file logger: {traceback.format_exc()}"
        print(msg_log_fail)
        if ui: ui.messageBox(msg_log_fail, CMD_NAME + " - Logging Error")

    try:
        if logger: logger.info(f"'{CMD_NAME}' run() called.")
        handlers.clear()

        push_cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if not push_cmd_def:
            push_cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "")

        on_cmd_created = GitCommandCreatedEventHandler()
        push_cmd_def.commandCreated.add(on_cmd_created)
        handlers.append(on_cmd_created)

        target_panel = ui.allToolbarPanels.itemById(PANEL_ID)
        if not target_panel:
            if logger: logger.info(f"Primary panel '{PANEL_ID}' not found. Trying fallbacks.")
            design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if design_workspace:
                for panel_id_option in [FALLBACK_PANEL_ID, "ToolsSolidPythonScriptsPanel", "FusionSolidScriptPanel"]:
                    tb_panel_candidate = design_workspace.toolbarPanels.itemById(panel_id_option)
                    if tb_panel_candidate:
                        target_panel = tb_panel_candidate
                        if logger: logger.info(f"Found fallback panel: '{target_panel.id}' ({target_panel.name})")
                        break

        if not target_panel:
            msg = f"Could not find a toolbar panel to add '{CMD_NAME}'."
            if ui: ui.messageBox(msg, "Add-In UI Error")
            if logger: logger.error(msg)
            adsk.autoTerminate(False)
            return

        _delete_all_controls(CONTROL_ID)

        try:
            git_push_control = target_panel.controls.addCommand(push_cmd_def, CONTROL_ID)
        except Exception as e_add:
            if logger: logger.warning("addCommand failed; attempting to reuse existing control. %s", str(e_add))
            git_push_control, _ = _find_control_anywhere(CONTROL_ID)
            if not (git_push_control and git_push_control.isValid):
                raise

        if git_push_control and git_push_control.isValid:
            git_push_control.isPromotedByDefault = True
            git_push_control.isPromoted = True
            git_push_control.isVisible = True
        else:
            msg = f"Command control '{CONTROL_ID}' is invalid after creation."
            if ui: ui.messageBox(msg, CMD_NAME)
            if logger: logger.error(msg)

        adsk.autoTerminate(False)
        is_initialized = True
        if logger: logger.info(f"'{CMD_NAME}' Add-In Loaded and running. {VERSION}")
    except Exception:
        error_msg = 'Failed to run the Add-In (run function)\n' + traceback.format_exc()
        if logger: logger.error(error_msg)
        else:
            if ui: ui.messageBox(error_msg, CMD_NAME + " - Critical Error")
            elif app: app.log(error_msg, adsk.core.LogLevels.CriticalLogLevel)
            else: print(error_msg)
        adsk.autoTerminate(True)

def stop(context):
    global push_cmd_def, git_push_control, handlers, app, ui, logger, is_initialized

    is_initialized = False

    current_app_ref = app
    current_ui_ref = ui
    if not current_app_ref or not current_ui_ref:
        try:
            temp_app_stop = adsk.core.Application.get()
            if temp_app_stop:
                if not current_app_ref: app = temp_app_stop; current_app_ref = temp_app_stop
                if not current_ui_ref: ui = temp_app_stop.userInterface; current_ui_ref = temp_app_stop.userInterface
            if not current_ui_ref:
                print("CRITICAL: Could not obtain UserInterface in stop(). Cannot stop cleanly.")
                if current_app_ref and logger: logger.critical("Could not obtain UserInterface in stop().")
                elif current_app_ref: current_app_ref.log("CRITICAL: Could not obtain UserInterface in stop().", adsk.core.LogLevels.CriticalLogLevel)
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in stop(): {traceback.format_exc()}")
            return

    log_stop_msg = f"'{CMD_NAME}' stop() called."
    if logger: logger.info(log_stop_msg)
    else: print(log_stop_msg)

    try:
        _delete_all_controls(CONTROL_ID)

        if git_push_control and git_push_control.isValid:
            git_push_control.deleteMe()
        if push_cmd_def and push_cmd_def.isValid:
            push_cmd_def.deleteMe()

        handlers.clear()

        if logger:
            logger.info(f"'{CMD_NAME}' Add-In Stopped. Shutting down logger.")
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)
            logger = None
    except Exception:
        error_msg = 'Failed to stop the Add-In cleanly (stop function)\n' + traceback.format_exc()
        if logger: logger.error(error_msg)
        else:
            if current_ui_ref: current_ui_ref.messageBox(error_msg, CMD_NAME + " - Stop Error")
            elif current_app_ref: current_app_ref.log(error_msg, adsk.core.LogLevels.ErrorLogLevel)
            else: print(error_msg)

