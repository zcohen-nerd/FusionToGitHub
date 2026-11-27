"""Push to GitHub — an Autodesk Fusion add-in.

Entry point: Fusion calls run() when the add-in starts and stop() when it
stops. This module creates the toolbar button and opens the dialog; the work
is done by:

- push_dialog.py      the dialog (inputs, validation, Edit/Remove, OK)
- push_controller.py  what happens after export: plan and push (no Fusion)
- push_worker.py      runs the push on a background thread (no Fusion)
- fusion_bridge.py    brings the worker's progress and questions to Fusion's main thread
- fusion_export.py    exporting the design (Fusion API)
- fusion_git_core.py  git: isolated commit and push (no Fusion)
- settings_store.py   saved settings and repositories (no Fusion)
- credentials.py      stored tokens (no Fusion)
- addin_logging.py    the log file and Fusion's text palette
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import List

# Execution mode (risk R-25). Fusion loads the add-in folder as a package and
# this file inside it, so the add-in's modules import each other relatively
# ("from . import push_dialog") and never by bare name. A bare name would
# reuse whatever module of that name is already loaded in Fusion's shared
# Python: a previous version of this add-in, or another add-in's module.
# Nothing is put on sys.path. push_cli.py and diagnostic.py are the
# standalone (command-line) entry points; this file is only for Fusion.
if not __package__:
    raise ImportError(
        "Push_To_GitHub.py is a Fusion add-in and must be loaded by Fusion as a package. "
        "For command-line use, run push_cli.py."
    )

ADDIN_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))


def _module_file(module) -> str:
    """A loaded module's file, read without running any of its code ("" if none)."""
    try:
        path = vars(module).get("__file__")
    except TypeError:  # not a normal module (some libraries put other objects in sys.modules)
        return ""
    return path if isinstance(path, str) else ""


def _module_dir(module) -> str:
    path = _module_file(module)
    return os.path.normcase(os.path.dirname(os.path.abspath(path))) if path else ""


def _forget_stale_modules() -> List[str]:
    """Forget this package's modules loaded before this file ran; return conflicts.

    When Fusion stops the add-in, the files are replaced (an update, a
    downgrade) and the add-in is run again in the same session, Python still
    holds the previous version's modules under this package's names and
    "from . import x" would return them. Only modules of this package that
    were loaded from this folder are removed (and bare-named modules an
    older version loaded from this folder); nothing else in sys.modules is
    touched. A module of this package loaded from a *different* folder means
    another add-in uses the same package name: it is left alone and reported.
    """
    prefix = __package__ + "."
    conflicts = []
    for name, module in list(sys.modules.items()):
        if module is None or name == __name__:
            continue
        if "." not in name and name != __package__:
            # Versions before 0.6.0 loaded their modules by bare name from this
            # folder ("fusion_git_core"). Forgetting those (and only those:
            # same folder, file named like the module) lets a later downgrade
            # to such a version load its own files. Bare-named modules from
            # anywhere else belong to someone else and are left alone.
            path = _module_file(module)
            if (path and _module_dir(module) == ADDIN_DIR
                    and os.path.splitext(os.path.basename(path))[0] == name):
                del sys.modules[name]
            continue
        if not name.startswith(prefix):
            continue
        where = _module_dir(module)
        if where and where != ADDIN_DIR:
            conflicts.append(f"{name} ({where})")
            continue
        del sys.modules[name]
        # "from . import x" reads the package's attribute x before
        # sys.modules, so the old module must be detached from the package too.
        short = name[len(prefix):]
        package = sys.modules.get(__package__)
        if package is not None and "." not in short and vars(package).get(short) is module:
            delattr(package, short)
    return conflicts


_CONFLICTS = _forget_stale_modules()
if _CONFLICTS:
    raise ImportError(
        f"Another add-in loaded modules under this add-in's package name '{__package__}' from a different "
        f"folder: {', '.join(_CONFLICTS)}. Remove the duplicate add-in folder and restart Fusion."
    )

import adsk.core  # noqa: E402
import adsk.fusion  # noqa: E402,F401
import adsk.cam  # noqa: E402,F401

from . import addin_logging  # noqa: E402
from .fusion_git_core import VERSION as CORE_VERSION  # noqa: E402

VERSION = CORE_VERSION
IS_WINDOWS = os.name == "nt"

# -----------------------------
# Config / constants
# -----------------------------
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")

# NOTE: the version suffix in this id is historical. Changing the id resets
# users' toolbar placement/promotion, so it stays frozen as VERSION advances.
CMD_ID = "PushToGitHub_Cmd_ZAC_V7_4"
CMD_NAME = "Push to GitHub"
CMD_TOOLTIP = "Exports/configures, updates changelog, and pushes design to GitHub."
PANEL_ID = "SolidUtilitiesAddinsPanel"
FALLBACK_PANEL_ID = "SolidScriptsAddinsPanel"
CONTROL_ID = CMD_ID + "_Control"

# -----------------------------
# Globals
# -----------------------------
app = None
ui = None
logger = None
handlers = []
# Handlers that only live as long as one command dialog. Kept separate so
# each dialog replaces the previous one's instead of accumulating forever.
dialog_handlers = []
push_cmd_def = None
git_push_control = None
is_initialized = False  # guard against double run()
# Where stored tokens live; None means "the platform default" (tests inject one).
credential_store = None
# fusion_bridge.WorkerBridge: background pushes and their custom event.
bridge = None
# False when another copy of the add-in already owns the button (duplicate install).
owns_command = False

THIS_FILE = os.path.normcase(os.path.abspath(__file__))
# The duplicate-install warning is shown once per load of this file.
_duplicate_warned = False


def _other_running_copy():
    """Folder of another loaded copy of this add-in that has the button, or None.

    A read-only look at loaded modules: an entry module of any version (0.3.x
    onward) defines the same CMD_ID, and says it is running through
    ``owns_command`` (0.6.0+) or ``is_initialized``. Attributes are read from
    each module's ``__dict__``, so no other module's code runs, and nothing
    is changed. A copy in this add-in's own folder is an earlier load of
    this add-in, not a duplicate.
    """
    me = sys.modules.get(__name__)
    for module in list(sys.modules.values()):
        if module is None or module is me:
            continue
        try:
            attrs = vars(module)
        except TypeError:
            continue
        if attrs.get("CMD_ID") != CMD_ID:
            continue
        running = attrs.get("owns_command", attrs.get("is_initialized"))
        if running is not True:
            continue
        if _module_dir(module) == ADDIN_DIR:
            continue
        path = _module_file(module)
        return os.path.dirname(os.path.abspath(path)) if path else "an unknown folder"
    return None

try:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    print(f"[PushToGitHub] Loaded {VERSION} with CMD_ID={CMD_ID}")
except (AttributeError, NameError):
    # NameError: adsk failed to import (outside Fusion);
    # AttributeError: Fusion API not fully initialised yet.
    pass


def _credentials():
    global credential_store
    if credential_store is None:
        from .credentials import default_store

        credential_store = default_store()
    return credential_store


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
        except Exception:
            if logger:
                logger.debug("Error searching panel for control '%s'", control_id, exc_info=True)
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
        except Exception:
            if logger:
                logger.debug("Error deleting control '%s' from panel", control_id, exc_info=True)


# -----------------------------
# UI: CommandCreated
# -----------------------------
class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        local_ui_ref = ui or adsk.core.Application.get().userInterface
        try:
            from . import push_dialog
            # A new dialog supersedes any previous one, so its handlers can
            # be released now (they are also cleared in run()/stop()).
            dialog_handlers.clear()
            ctx = push_dialog.DialogContext(
                app=app or adsk.core.Application.get(),
                ui=local_ui_ref,
                title=CMD_NAME,
                settings_path=CONFIG_PATH,
                repo_base_dir=REPO_BASE_DIR,
                credentials=_credentials(),
                logger=logger,
                handlers=dialog_handlers,
                bridge=bridge,
            )
            push_dialog.open_dialog(ctx, args.command)
        except Exception:
            if local_ui_ref:
                local_ui_ref.messageBox(f"GitCommandCreatedEventHandler failed:\n{traceback.format_exc()}", CMD_NAME)
            if logger:
                logger.exception("GitCommandCreatedEventHandler failed")


# -----------------------------
# Lifecycle
# -----------------------------
def _find_target_panel():
    target_panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if target_panel:
        return target_panel
    if logger:
        logger.info(f"Primary panel '{PANEL_ID}' not found. Trying fallbacks.")
    design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")
    if design_workspace:
        for panel_id_option in [FALLBACK_PANEL_ID, "ToolsSolidPythonScriptsPanel", "FusionSolidScriptPanel"]:
            candidate = design_workspace.toolbarPanels.itemById(panel_id_option)
            if candidate:
                if logger:
                    logger.info(f"Found fallback panel: '{candidate.id}' ({candidate.name})")
                return candidate
    return None


def _report_duplicate(other_folder) -> None:
    """Another copy of the add-in has the button: say so (once per load)."""
    global _duplicate_warned
    msg = (
        f"Another copy of '{CMD_NAME}' is already running, so this copy won't add a second button."
        f"\n\nThe running copy is in:\n{other_folder}\n\nThis copy is in:\n{os.path.dirname(THIS_FILE)}\n\n"
        "Remove one of them in Utilities > Add-Ins > Scripts and Add-Ins, then restart Fusion."
    )
    if logger:
        logger.warning(msg)
    if _duplicate_warned:
        return
    _duplicate_warned = True
    if ui:
        ui.messageBox(msg, CMD_NAME)


def run(context):
    global push_cmd_def, git_push_control, app, ui, logger, is_initialized, bridge, owns_command

    if not app or not ui:
        try:
            temp_app = adsk.core.Application.get()
            if temp_app:
                app = temp_app
                ui = temp_app.userInterface
            if not ui:
                print("CRITICAL: Could not obtain UserInterface in run().")
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in run(): {traceback.format_exc()}")
            return

    if is_initialized:
        if logger:
            logger.info("Add-in already initialized; skipping toolbar injection.")
        adsk.autoTerminate(False)
        return

    try:
        logger = addin_logging.setup_logger(CMD_ID, app, adsk.core.LogLevels, CMD_NAME)
    except Exception:
        msg_log_fail = f"CRITICAL: Failed to setup file logger: {traceback.format_exc()}"
        print(msg_log_fail)
        if ui:
            ui.messageBox(msg_log_fail, CMD_NAME + " - Logging Error")

    try:
        if logger:
            logger.info(f"'{CMD_NAME}' run() called.")
        handlers.clear()
        dialog_handlers.clear()

        existing = ui.commandDefinitions.itemById(CMD_ID)
        if existing:
            other = _other_running_copy()
            if other is not None:
                # Another installed copy (of any version) has the button: leave it alone.
                owns_command = False
                _report_duplicate(other)
                adsk.autoTerminate(False)
                return
            # Left by an earlier load of this add-in that didn't stop cleanly
            # (or by a copy that is no longer running): start afresh.
            _delete_all_controls(CONTROL_ID)
            existing.deleteMe()
        push_cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "")
        owns_command = True

        from . import fusion_bridge
        bridge = fusion_bridge.WorkerBridge(app, ui, CMD_ID + fusion_bridge.EVENT_SUFFIX, CMD_NAME, logger)
        if not bridge.register() and logger:
            logger.error("Background pushes are unavailable: the custom event could not be registered.")

        on_cmd_created = GitCommandCreatedEventHandler()
        push_cmd_def.commandCreated.add(on_cmd_created)
        handlers.append(on_cmd_created)

        target_panel = _find_target_panel()
        if not target_panel:
            msg = f"Could not find a toolbar panel to add '{CMD_NAME}'."
            ui.messageBox(msg, "Add-In UI Error")
            if logger:
                logger.error(msg)
            adsk.autoTerminate(False)
            return

        _delete_all_controls(CONTROL_ID)
        try:
            git_push_control = target_panel.controls.addCommand(push_cmd_def, CONTROL_ID)
        except Exception as e_add:
            if logger:
                logger.warning("addCommand failed; attempting to reuse existing control. %s", str(e_add))
            git_push_control, _ = _find_control_anywhere(CONTROL_ID)
            if not (git_push_control and git_push_control.isValid):
                raise

        if git_push_control and git_push_control.isValid:
            git_push_control.isPromotedByDefault = True
            git_push_control.isPromoted = True
            git_push_control.isVisible = True
        else:
            msg = f"Command control '{CONTROL_ID}' is invalid after creation."
            ui.messageBox(msg, CMD_NAME)
            if logger:
                logger.error(msg)

        adsk.autoTerminate(False)
        is_initialized = True
        if logger:
            logger.info(f"'{CMD_NAME}' Add-In Loaded and running. {VERSION}")
    except Exception:
        error_msg = "Failed to run the Add-In (run function)\n" + traceback.format_exc()
        if logger:
            logger.error(error_msg)
        elif ui:
            ui.messageBox(error_msg, CMD_NAME + " - Critical Error")
        else:
            print(error_msg)
        adsk.autoTerminate(True)


def stop(context):
    global push_cmd_def, git_push_control, app, ui, logger, is_initialized, bridge, owns_command

    is_initialized = False
    if not app or not ui:
        try:
            temp_app = adsk.core.Application.get()
            if temp_app:
                app = app or temp_app
                ui = ui or temp_app.userInterface
            if not ui:
                print("CRITICAL: Could not obtain UserInterface in stop(). Cannot stop cleanly.")
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in stop(): {traceback.format_exc()}")
            return

    if logger:
        logger.info(f"'{CMD_NAME}' stop() called.")
    else:
        print(f"'{CMD_NAME}' stop() called.")

    try:
        if bridge is not None:
            # Cancel a running push and wait briefly; its temporary files are
            # removed by the worker thread when it ends.
            if not bridge.close() and logger:
                logger.warning("A push was still finishing when the add-in stopped.")
            bridge = None
        if owns_command:
            _delete_all_controls(CONTROL_ID)
            if git_push_control and git_push_control.isValid:
                git_push_control.deleteMe()
            if push_cmd_def and push_cmd_def.isValid:
                push_cmd_def.deleteMe()
        owns_command = False
        git_push_control = None
        push_cmd_def = None
        handlers.clear()
        dialog_handlers.clear()
        if logger:
            logger.info(f"'{CMD_NAME}' Add-In Stopped. Shutting down logger.")
        addin_logging.shutdown_logger()
        logger = None
    except Exception:
        error_msg = "Failed to stop the Add-In cleanly (stop function)\n" + traceback.format_exc()
        if logger:
            logger.error(error_msg)
        elif ui:
            ui.messageBox(error_msg, CMD_NAME + " - Stop Error")
        else:
            print(error_msg)

