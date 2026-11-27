"""Push to GitHub — an Autodesk Fusion add-in.

Entry point: Fusion calls run() when the add-in starts and stop() when it
stops. This module creates the toolbar button and opens the dialog; the work
is done by:

- push_dialog.py      the dialog (inputs, validation, Edit/Remove, OK)
- push_controller.py  what happens after export: plan and push (no Fusion)
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

# Fusion API — only available inside Fusion (or with tests/fakes on sys.path).
try:
    import adsk.core
    import adsk.fusion  # noqa: F401
    import adsk.cam  # noqa: F401
except ImportError:
    pass

# Sibling modules: when Fusion loads the add-in, its folder may not be on
# sys.path yet.
try:
    import addin_logging
    from fusion_git_core import VERSION as CORE_VERSION
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    import addin_logging
    from fusion_git_core import VERSION as CORE_VERSION

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
        from credentials import default_store

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
            import push_dialog

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


def run(context):
    global push_cmd_def, git_push_control, app, ui, logger, is_initialized

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

        push_cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if not push_cmd_def:
            push_cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "")

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
    global push_cmd_def, git_push_control, app, ui, logger, is_initialized

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
        _delete_all_controls(CONTROL_ID)
        if git_push_control and git_push_control.isValid:
            git_push_control.deleteMe()
        if push_cmd_def and push_cmd_def.isValid:
            push_cmd_def.deleteMe()
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

