"""The "Push to GitHub" command dialog.

``PushDialog`` owns the dialog's inputs and state. The Fusion event-handler
classes at the bottom are thin wrappers: they call a ``PushDialog`` method
and never let an exception escape (an exception escaping a Fusion handler
silently breaks the dialog).

Everything after "the design is exported" is decided by
``push_controller.PushController``, which has no Fusion dependency. The git
part then runs on a background thread (``push_worker``), and its progress,
questions and summary come back to Fusion's main thread through
``fusion_bridge``; the dialog has closed by then. Settings
go through ``settings_store.SettingsStore`` and tokens through a
``credentials.CredentialStore``, both injected via ``DialogContext`` so tests
can run the dialog against the simulated Fusion API in tests/fakes.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import adsk.core
import adsk.fusion  # noqa: F401  (Design type checks happen in fusion_export)

from . import addin_logging
from .credentials import CredentialError, CredentialStore
from .dialog_helpers import (
    convert_github_url,
    default_path_for_new_repo,
    derive_repo_name_from_url,
    normalize_export_subfolder,
    resolve_new_repo_path,
    setup_new_repository,
    validate_repo_inputs,
)
from .fusion_export import (
    AVAILABLE_FORMATS,
    DEFAULT_FORMATS,
    FORMAT_SETTING_LABELS,
    FORMAT_SETTINGS_DEFAULT,
    FORMAT_SETTINGS_OPTIONS,
    _safe_base,
    design_identity,
    determine_valid_export_formats,
    export_design,
    get_fusion_design,
    linked_components_note,
    linked_components_question,
    temporary_export_dir,
)
from . import push_worker
from .fusion_bridge import BUSY_TEXT, NOTHING_PUSHED, PushJob, WorkerBusy
from .fusion_git_core import (
    GitError,
    export_size_check,
    git_available,
    git_run,
    redact_secrets,
    sanitize_branch_name,
)
from .push_controller import (
    DEFAULT_BRANCH_FORMAT,
    DEFAULT_COMMIT_TEMPLATE,
    PushCancelled,
    PushController,
    PushRefused,
    PushRequest,
)
from .settings_store import SettingsError, SettingsStore

ADD_NEW_OPTION = "🆕 Set up new GitHub repository..."
DIALOG_TITLE_CONFIG_ERROR = "Config Error"
DIALOG_TITLE_GIT_NOT_FOUND = "Git Not Found"


@dataclass
class DialogContext:
    """What the dialog needs from the add-in; injected so tests can replace it."""

    app: Any
    ui: Any
    title: str
    settings_path: str
    repo_base_dir: str
    credentials: CredentialStore
    logger: Optional[logging.Logger] = None
    handlers: List[Any] = field(default_factory=list)
    # fusion_bridge.WorkerBridge that runs pushes in the background.
    bridge: Any = None


class FusionCommandGitUI:
    """GitUI for fusion_git_core: logs, and shows warnings, errors and questions in Fusion."""

    def __init__(self, ui_ref, title: str, logger: Optional[logging.Logger] = None):
        self._ui = ui_ref
        self._title = title
        self._logger = logger

    def info(self, message: str) -> None:
        if self._logger:
            self._logger.info(message)

    def warn(self, message: str) -> None:
        if self._logger:
            self._logger.warning(message)
        if self._ui:
            self._ui.messageBox(message, self._title)

    def error(self, message: str) -> None:
        if self._logger:
            self._logger.error(message)
        if self._ui:
            self._ui.messageBox(message, self._title)

    def confirm(self, message: str) -> bool:
        if not self._ui:
            return False
        result = self._ui.messageBox(message, self._title, adsk.core.MessageBoxButtonTypes.YesNoButtonType)
        return result == adsk.core.DialogResults.DialogYes


def check_git_available(target_ui_ref, logger: Optional[logging.Logger] = None) -> bool:
    try:
        if git_available():
            return True
    except (OSError, RuntimeError):
        pass
    msg = "Git executable not found or not working. Check PATH or install Git."
    target_ui_ref.messageBox(msg, DIALOG_TITLE_GIT_NOT_FOUND)
    if logger:
        logger.error(msg)
    return False


class PushDialog:
    """One open "Push to GitHub" dialog: its inputs, its state and its actions."""

    def __init__(self, ctx: DialogContext, command):
        self.ctx = ctx
        self.command = command
        self.ui = ctx.ui
        self.title = ctx.title
        self.logger = ctx.logger
        self.creds = ctx.credentials
        self.store = SettingsStore(ctx.settings_path)
        self.load_report = self.store.load()
        self.controller = PushController(self.store, self.creds, self.logger)
        self.git_ui = FusionCommandGitUI(self.ui, self.title, self.logger)
        self.format_settings_state: Dict[str, Dict[str, str]] = {}
        self.format_setting_inputs: Dict[str, Any] = {}
        # Inputs built for the settings table, so each rebuild can delete
        # them: TableCommandInput.clear() only detaches rows, the inputs
        # survive in the command and their ids would collide.
        self.format_settings_ui = {"inputs": [], "generation": 0}
        self.auto_path = True
        self.format_settings_table = None

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def message(self, text: str, title: Optional[str] = None) -> None:
        self.ui.messageBox(text, title or self.title)

    def ask_yes_no(self, text: str) -> bool:
        return self.git_ui.confirm(text)

    def save_settings(self) -> bool:
        """Save; show the reason and return False if the settings can't be saved."""
        try:
            self.store.save()
            return True
        except (SettingsError, OSError) as exc:
            self.message(f"Settings were not saved:\n{exc}", DIALOG_TITLE_CONFIG_ERROR)
            if self.logger:
                self.logger.error("Settings save failed: %s", exc)
            return False

    @property
    def meta(self) -> Dict[str, Any]:
        return self.store.meta

    def selected_repo_name(self) -> str:
        sel = self.repo_selector.selectedItem
        return sel.name if sel else ADD_NEW_OPTION

    # ------------------------------------------------------------------
    # Building the dialog
    # ------------------------------------------------------------------

    def build(self) -> None:
        cmd = self.command
        cmd.isAutoExecute = False
        cmd.isAutoTerminate = True
        inputs = self.inputs = cmd.commandInputs
        meta = self.meta

        repo_group = inputs.addGroupCommandInput("repoGroup", "Repository")
        repo_group.isExpanded = True
        repo_inputs = self.repo_inputs = repo_group.children

        self.repo_selector = repo_inputs.addDropDownCommandInput(
            "repoSelector", "Select Repository", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        self._fill_repo_selector(meta.get("lastSelectedRepo"))

        self.new_repo_name_input = repo_inputs.addStringValueInput("newRepoName", "Repository Name", "")
        self.git_url_input = repo_inputs.addStringValueInput(
            "gitUrl", "GitHub URL", "https://github.com/yourcompany/projectname"
        )
        self.repo_path_input = repo_inputs.addStringValueInput("repoPath", "Local Folder", "")
        self.browse_repo_button = repo_inputs.addBoolValueInput("browseRepoPath", "Browse…", False, "", False)
        self.browse_repo_button.isFullWidth = False
        self.repo_status_input = repo_inputs.addTextBoxCommandInput("repoValidationStatus", "", "", 2, True)
        self.repo_status_input.isFullWidth = True
        self.git_status_input = repo_inputs.addTextBoxCommandInput("gitValidationStatus", "", "", 2, True)
        self.git_status_input.isFullWidth = True
        self.conversion_status_input = repo_inputs.addTextBoxCommandInput("conversionStatus", "", "", 2, True)
        self.conversion_status_input.isFullWidth = True
        self.help_text_input = repo_inputs.addTextBoxCommandInput(
            "helpText",
            "",
            "💡 Quick Setup: \n1) Paste your GitHub repository URL above\n2) Choose a folder using "
            "Browse button\n3) Click OK - everything else is automatic!",
            3,
            True,
        )
        self.help_text_input.isFullWidth = True

        # Edit / Remove a saved repository.
        self.edit_repo_button = repo_inputs.addBoolValueInput("editRepo", "Edit Repository…", False, "", False)
        self.edit_repo_button.isFullWidth = True
        self.remove_repo_button = repo_inputs.addBoolValueInput("removeRepo", "Remove Repository…", False, "", False)
        self.remove_repo_button.isFullWidth = True
        self.remove_repo_button.tooltip = (
            "Forget this saved repository. The local folder, the GitHub repository and its "
            "history are not touched."
        )
        self.edit_name_input = repo_inputs.addStringValueInput("editRepoName", "Name", "")
        self.edit_url_input = repo_inputs.addStringValueInput("editGitUrl", "GitHub URL", "")
        self.edit_path_input = repo_inputs.addStringValueInput("editRepoPath", "Local Folder", "")
        self.edit_browse_button = repo_inputs.addBoolValueInput("editBrowse", "Browse…", False, "", False)
        self.edit_save_button = repo_inputs.addBoolValueInput("saveRepoEdit", "Save Changes", False, "", False)
        self.edit_save_button.isFullWidth = True
        self.edit_inputs = [
            self.edit_name_input, self.edit_url_input, self.edit_path_input,
            self.edit_browse_button, self.edit_save_button,
        ]

        current_selection = self.selected_repo_name()
        self.update_new_repo_visibility(current_selection)

        # Commit message — top-level, always visible
        inputs.addStringValueInput("commitMsgPush", "Commit Message", meta.get("lastCommitMessage", "Updated design"))

        # Export formats — collapsed for returning users
        export_group = inputs.addGroupCommandInput("exportGroup", "Export Formats")
        export_group.isExpanded = current_selection == ADD_NEW_OPTION
        self.export_inputs = export_group.children
        self.export_formats_dropdown = self.export_inputs.addDropDownCommandInput(
            "exportFormatsConfig", "Export Formats", adsk.core.DropDownStyles.CheckBoxDropDownStyle
        )
        for fmt in AVAILABLE_FORMATS:
            self.export_formats_dropdown.listItems.add(fmt, fmt in DEFAULT_FORMATS, "")

        # addTableCommandInput's signature differs across Fusion API
        # versions: try the 4-arg form, then the 3-arg form, otherwise run
        # without the settings table (defaults still apply).
        try:
            self.format_settings_table = self.export_inputs.addTableCommandInput(
                "formatSettingsTable", "Format Settings", 2, "1:1"
            )
        except Exception:
            try:
                self.format_settings_table = self.export_inputs.addTableCommandInput(
                    "formatSettingsTable", "Format Settings", 2
                )
            except Exception:
                if self.logger:
                    self.logger.warning(
                        "Could not create format settings table; using default format settings.", exc_info=True
                    )
        if self.format_settings_table:
            self.format_settings_table.maximumVisibleRows = len(AVAILABLE_FORMATS) + 1
            self.format_settings_table.columnSpacing = 4
            self.format_settings_table.rowSpacing = 2

        # Templates — rarely changed, collapsed by default
        git_group = inputs.addGroupCommandInput("gitGroup", "Templates")
        git_group.isExpanded = False
        git_inputs = git_group.children
        git_inputs.addStringValueInput("defaultMessageConfig", "Commit Template", DEFAULT_COMMIT_TEMPLATE)
        git_inputs.addStringValueInput("branchFormatConfig", "Branch Name Template", DEFAULT_BRANCH_FORMAT)

        flow_group = inputs.addGroupCommandInput("flowGroup", "Advanced")
        flow_group.isExpanded = False
        flow_inputs = flow_group.children
        flow_inputs.addStringValueInput("exportSubfolder", "Export Subfolder", "")
        branch_override_input = flow_inputs.addStringValueInput("branchPreview", "Branch Name Override", "")
        branch_override_input.tooltip = (
            "Leave blank to auto-generate the branch name from the branch template. Enter a name "
            "to push to that specific branch instead (reusing it if it already exists)."
        )
        tokens_supported = bool(getattr(self.creds, "available", False))
        self.use_pat_input = flow_inputs.addBoolValueInput("useStoredPat", "Use Stored Token", True, "", False)
        self.use_pat_input.isFullWidth = False
        self.use_pat_input.isVisible = tokens_supported
        self.manage_pat_button = flow_inputs.addBoolValueInput("managePat", "Manage Token…", False, "", False)
        self.manage_pat_button.isFullWidth = True
        self.manage_pat_button.isVisible = tokens_supported

        # Token entry, shown by "Manage Token…". The token field is a
        # password field, so the token is never visible on screen (audit
        # SEC-07); it is cleared as soon as it has been saved.
        self.pat_username_input = flow_inputs.addStringValueInput("patUsername", "Token Username", "")
        self.pat_username_input.tooltip = "Optional. Leave blank for a GitHub personal access token."
        self.pat_token_input = flow_inputs.addStringValueInput("patToken", "Token", "")
        try:
            self.pat_token_input.isPassword = True
        except Exception:
            if self.logger:
                self.logger.warning("This Fusion version can't mask the token field.")
        self.pat_token_input.tooltip = "Paste the token. It is stored in Windows Credential Manager."
        self.pat_save_button = flow_inputs.addBoolValueInput("patSave", "Save Token", False, "", False)
        self.pat_save_button.isFullWidth = True
        for entry_input in (self.pat_username_input, self.pat_token_input, self.pat_save_button):
            entry_input.isVisible = False

        self.flow_status_input = flow_inputs.addTextBoxCommandInput("flowValidationStatus", "", "", 2, True)
        self.flow_status_input.isFullWidth = True

        log_group = inputs.addGroupCommandInput("logGroup", "Logging & Privacy")
        log_group.isExpanded = False
        log_inputs = log_group.children
        self.log_level_dropdown = log_inputs.addDropDownCommandInput(
            "logLevel", "Log Level", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        for level_name in ["ERROR", "WARNING", "INFO", "DEBUG"]:
            self.log_level_dropdown.listItems.add(level_name, level_name == addin_logging.current_log_level_name, "")
        open_log_button = log_inputs.addBoolValueInput("openLogFile", "Open Log File…", False, "", False)
        open_log_button.isFullWidth = True
        clear_log_button = log_inputs.addBoolValueInput("clearLogFile", "Clear Log", False, "", False)
        clear_log_button.isFullWidth = True
        clear_log_button.tooltip = (
            "Delete the add-in's log files. They contain folder paths, repository addresses and Git messages."
        )
        privacy_button = log_inputs.addBoolValueInput("openPrivacy", "Privacy Policy…", False, "", False)
        privacy_button.isFullWidth = True
        privacy_button.tooltip = "What this add-in stores and sends, and how to delete it."

        self.sync_format_settings_rows()
        if current_selection != ADD_NEW_OPTION:
            self.apply_repo_settings(current_selection)
        self.ensure_new_repo_defaults()

    def show_load_messages(self) -> None:
        """Explain, once, anything unusual that happened while loading settings."""
        if self.load_report.messages:
            self.message("\n\n".join(self.load_report.messages), DIALOG_TITLE_CONFIG_ERROR)
            for text in self.load_report.messages:
                if self.logger:
                    self.logger.warning("Settings: %s", text)

    def _fill_repo_selector(self, preferred: Optional[str]) -> None:
        """(Re)fill the repository dropdown, selecting *preferred* when it exists."""
        names = self.store.profile_names()
        items = self.repo_selector.listItems
        items.clear()
        selected = preferred if preferred in names else ADD_NEW_OPTION
        # Always show "Add new repo" first, even if saved repos exist.
        for name in [ADD_NEW_OPTION] + names:
            items.add(name, name == selected, "")
        if self.repo_selector.selectedItem is None and items.count:
            items.item(0).isSelected = True

    def update_new_repo_visibility(self, selection_name: str) -> None:
        show_new_repo = selection_name == ADD_NEW_OPTION
        for item in (
            self.new_repo_name_input, self.git_url_input, self.git_status_input, self.help_text_input,
            # Saved repositories keep their folder in settings; the path
            # field is only shown while setting up a new one.
            self.repo_path_input, self.browse_repo_button, self.repo_status_input,
            self.conversion_status_input,
        ):
            item.isVisible = show_new_repo
        self.edit_repo_button.isVisible = not show_new_repo
        self.remove_repo_button.isVisible = not show_new_repo
        self.show_edit_fields(False)
        if hasattr(self, "pat_token_input"):
            self.show_pat_entry(False)

    # ------------------------------------------------------------------
    # Export format settings table
    # ------------------------------------------------------------------

    def get_selected_formats(self) -> List[str]:
        return [item.name for item in self.export_formats_dropdown.listItems if item.isSelected]

    def ensure_format_defaults(self, fmt: str) -> None:
        fmt_state = self.format_settings_state.setdefault(fmt, {})
        for key, value in FORMAT_SETTINGS_DEFAULT.get(fmt, {}).items():
            fmt_state.setdefault(key, value)

    def sync_format_settings_rows(self) -> None:
        table = self.format_settings_table
        if not table:
            return
        table.clear()
        for stale_input in self.format_settings_ui["inputs"]:
            try:
                stale_input.deleteMe()
            except Exception:
                if self.logger:
                    self.logger.debug("Failed to delete stale format settings input", exc_info=True)
        self.format_settings_ui["inputs"] = []
        self.format_setting_inputs.clear()
        self.format_settings_ui["generation"] += 1
        generation = self.format_settings_ui["generation"]
        export_inputs = self.export_inputs

        header_label = export_inputs.addTextBoxCommandInput(f"formatSettingsHeaderLabel_g{generation}", "", "Format", 1, True)
        header_label.isFullWidth = True
        header_setting = export_inputs.addTextBoxCommandInput(
            f"formatSettingsHeaderSetting_g{generation}", "", "Setting", 1, True
        )
        header_setting.isFullWidth = True
        self.format_settings_ui["inputs"].extend([header_label, header_setting])
        table.addCommandInput(header_label, 0, 0)
        table.addCommandInput(header_setting, 0, 1)

        # One row per setting: STL has two (mesh refinement, files).
        row_index = 1
        for fmt in self.get_selected_formats():
            self.ensure_format_defaults(fmt)
            current_state = self.format_settings_state.get(fmt, {})
            for state_key, options in FORMAT_SETTINGS_OPTIONS.get(fmt, {}).items():
                row_key = f"{fmt}_{state_key}"
                label_text = FORMAT_SETTING_LABELS.get((fmt, state_key), fmt.upper())
                label = export_inputs.addTextBoxCommandInput(
                    f"formatSettingsLabel_{row_key}_g{generation}", "", label_text, 1, True
                )
                label.isFullWidth = True
                dropdown = export_inputs.addDropDownCommandInput(
                    f"formatSetting_{row_key}_g{generation}", "", adsk.core.DropDownStyles.TextListDropDownStyle
                )
                dropdown.listItems.clear()
                current_value = current_state.get(state_key, FORMAT_SETTINGS_DEFAULT.get(fmt, {}).get(state_key))
                for option_label, value in options:
                    dropdown.listItems.add(option_label, value == current_value, "")
                self.format_setting_inputs[row_key] = (fmt, dropdown, state_key, options)
                self.format_settings_ui["inputs"].extend([label, dropdown])
                table.addCommandInput(label, row_index, 0)
                table.addCommandInput(dropdown, row_index, 1)
                row_index += 1

    def collect_format_settings_from_ui(self) -> Dict[str, Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}
        for fmt, dropdown, state_key, options in self.format_setting_inputs.values():
            selected_item = dropdown.selectedItem
            if not selected_item:
                continue
            result.setdefault(fmt, {})[state_key] = dict(options).get(selected_item.name, selected_item.name)
        return result

    def update_export_subfolder_feedback(self, raw_value: str) -> str:
        try:
            normalized = normalize_export_subfolder(raw_value)
            if normalized:
                hint = f"✅ Exports will be copied to repo/{normalized}"
                if "{filename}" in normalized or "{timestamp}" in normalized:
                    hint += " (placeholders filled at export time)"
                self.flow_status_input.text = hint
            else:
                self.flow_status_input.text = ""
            return normalized
        except ValueError as exc:
            self.flow_status_input.text = f"❌ {exc}"
            return raw_value

    # ------------------------------------------------------------------
    # Repository selection and validation
    # ------------------------------------------------------------------

    def apply_repo_settings(self, repo_name: str) -> None:
        det = self.store.get(repo_name) or {}
        inputs = self.inputs
        saved_formats = set(det.get("exportFormats", []))
        for item in self.export_formats_dropdown.listItems:
            is_saved = item.name in saved_formats if saved_formats else False
            item.isSelected = is_saved or (not saved_formats and item.name in DEFAULT_FORMATS)

        self.format_settings_state.clear()
        saved_settings = det.get("formatSettings", {})
        if isinstance(saved_settings, dict):
            self.format_settings_state.update(saved_settings)
        self.sync_format_settings_rows()

        inputs.itemById("defaultMessageConfig").value = det.get("defaultMessage", DEFAULT_COMMIT_TEMPLATE)
        inputs.itemById("branchFormatConfig").value = det.get("branchFormat", DEFAULT_BRANCH_FORMAT)
        self.repo_path_input.value = det.get("path", "")
        self.git_url_input.value = det.get("url", "")
        export_subfolder_value = det.get("exportSubfolder", "")
        inputs.itemById("exportSubfolder").value = export_subfolder_value

        if self.creds.available:
            self.use_pat_input.value = bool(det.get("useStoredPat", False))
        # A half-entered token never carries over to another repository.
        self.pat_token_input.value = ""
        for entry_input in (self.pat_username_input, self.pat_token_input, self.pat_save_button):
            entry_input.isVisible = False

        repo_log_level = det.get("logLevel") or self.meta.get("globalLogLevel") or addin_logging.current_log_level_name
        for item in self.log_level_dropdown.listItems:
            item.isSelected = item.name == repo_log_level

        # Branch override is opt-in per push: pre-filling it with a previous
        # branch name made every second push collide.
        inputs.itemById("branchPreview").value = ""
        self.update_export_subfolder_feedback(export_subfolder_value)

    def update_validation(self, selection_name: Optional[str] = None) -> Dict[str, Any]:
        selected = selection_name or self.selected_repo_name()
        validation = validate_repo_inputs(
            selected,
            self.repo_path_input.value,
            # Validate the converted URL: the field keeps the user's text and
            # is only converted when OK is clicked.
            convert_github_url(self.git_url_input.value) if selected == ADD_NEW_OPTION else "",
            ADD_NEW_OPTION,
        )
        self.repo_status_input.text = validation["messages"]["path"][0]
        self.git_status_input.text = validation["messages"]["git"][0] if selected == ADD_NEW_OPTION else ""
        return validation

    def ensure_new_repo_defaults(self) -> None:
        if self.selected_repo_name() == ADD_NEW_OPTION:
            if self.auto_path:
                self.repo_path_input.value = default_path_for_new_repo(
                    self.new_repo_name_input.value.strip(), self.ctx.repo_base_dir, _safe_base
                )
            self.format_settings_state.clear()
            self.sync_format_settings_rows()
            self.inputs.itemById("exportSubfolder").value = ""
            if self.creds.available:
                self.use_pat_input.value = False
            self.inputs.itemById("branchPreview").value = ""
            self.flow_status_input.text = ""
            level = self.meta.get("globalLogLevel") or addin_logging.current_log_level_name
            for item in self.log_level_dropdown.listItems:
                item.isSelected = item.name == level
        self.update_validation()

    def on_git_url_changed(self) -> None:
        # Show what the URL converts to without touching the field itself —
        # rewriting it on every keystroke mangled typed input. The actual
        # conversion (and repo name derivation) happens on OK.
        current_url = self.git_url_input.value.strip()
        hints = []
        if current_url:
            converted = convert_github_url(current_url)
            if converted != current_url:
                hints.append(f"✅ Will use: {converted}")
            derived_name = derive_repo_name_from_url(converted)
            if derived_name and not self.new_repo_name_input.value.strip():
                hints.append(f"Repository name: {derived_name}")
        self.conversion_status_input.text = "\n".join(hints)
        self.update_validation()

    # ------------------------------------------------------------------
    # Stored token
    # ------------------------------------------------------------------

    def show_pat_entry(self, visible: bool, existing_username: str = "") -> None:
        """Show or hide the masked token fields; always clears the token field."""
        self.pat_token_input.value = ""
        if visible:
            self.pat_username_input.value = existing_username or ""
        for entry_input in (self.pat_username_input, self.pat_token_input, self.pat_save_button):
            entry_input.isVisible = visible and self.creds.available
        self.flow_status_input.text = "Paste the token into the Token field, then click Save Token." if visible else ""

    def save_pat_entry(self, repo_name: str) -> None:
        token_value = (self.pat_token_input.value or "").strip()
        if not token_value:
            self.message("Paste a token into the Token field first.")
            return
        try:
            host = self.controller.store_token(repo_name, (self.pat_username_input.value or "").strip(), token_value)
        except (CredentialError, PushRefused, OSError) as exc:
            if self.logger:
                self.logger.error("Could not store the token: %s", redact_secrets(str(exc), [token_value]))
            self.message(f"The token couldn't be stored:\n{redact_secrets(str(exc), [token_value])}")
            return
        finally:
            self.pat_token_input.value = ""  # never keep the token in the dialog
        self.show_pat_entry(False)
        self.use_pat_input.value = True
        self.message(
            f"Token saved in Windows Credential Manager for {host}. It is only ever sent to that "
            "server, over https."
        )

    def manage_pat_for_repo(self, repo_name: str) -> None:
        if not self.creds.available:
            self.message("PAT storage is only available on Windows.")
            return
        if self.pat_save_button.isVisible:
            # Clicking "Manage Token…" again cancels the entry.
            self.show_pat_entry(False)
            return
        try:
            existing = self.creds.get(repo_name)
        except CredentialError as exc:
            self.message(f"Windows Credential Manager couldn't be read:\n{exc}")
            return
        if existing:
            choice = self.ui.messageBox(
                "A stored token already exists for this repository.\n\n"
                "Yes: Replace it\nNo: Delete it\nCancel: Leave it unchanged",
                self.title,
                adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
            )
            if choice == adsk.core.DialogResults.DialogYes:
                self.show_pat_entry(True, existing.get("username", ""))
            elif choice == adsk.core.DialogResults.DialogNo:
                try:
                    self.creds.delete(repo_name)
                except CredentialError as exc:
                    self.message(f"The stored token couldn't be deleted:\n{exc}")
                    return
                self.message(
                    "Stored token deleted from this computer. It still works on GitHub until you revoke "
                    "it there (GitHub → Settings → Developer settings)."
                )
                self.use_pat_input.value = False
            return
        if self.ask_yes_no("No stored token for this repository. Add one now?"):
            self.show_pat_entry(True)

    def on_use_stored_pat_changed(self) -> None:
        repo_name = self.selected_repo_name()
        if repo_name == ADD_NEW_OPTION:
            self.message("Add the repository before enabling stored PAT usage.")
            self.use_pat_input.value = False
        elif self.use_pat_input.value:
            try:
                found = self.creds.get(repo_name)
            except CredentialError as exc:
                self.message(f"Windows Credential Manager couldn't be read:\n{exc}")
                found = None
            if not found:
                self.message("No stored token was found. Use 'Manage Token…' to add one first.")
                self.use_pat_input.value = False

    # ------------------------------------------------------------------
    # Edit / remove a saved repository
    # ------------------------------------------------------------------

    def show_edit_fields(self, visible: bool) -> None:
        for item in self.edit_inputs:
            item.isVisible = visible

    def toggle_edit(self) -> None:
        name = self.selected_repo_name()
        if name == ADD_NEW_OPTION:
            return
        if self.edit_save_button.isVisible:
            self.show_edit_fields(False)  # pressing Edit again cancels
            return
        profile = self.store.get(name) or {}
        self.edit_name_input.value = name
        self.edit_url_input.value = profile.get("url", "")
        self.edit_path_input.value = profile.get("path", "")
        self.show_edit_fields(True)

    def save_edit(self) -> None:
        name = self.selected_repo_name()
        if name == ADD_NEW_OPTION:
            return
        new_name = self.edit_name_input.value.strip()
        new_url = convert_github_url(self.edit_url_input.value.strip())
        new_path = self.edit_path_input.value.strip()

        def update_origin(repo_path: str, old_url: str, url: str) -> bool:
            return self.ask_yes_no(
                f"Also point the local folder's Git remote to the new address?\n\n{url}\n\n"
                "Choose No to keep the folder connected to its current address."
            )

        try:
            final_name, notes = self.controller.edit_profile(
                name, new_name=new_name, url=new_url, path=new_path, update_origin=update_origin
            )
        except (SettingsError, CredentialError, OSError) as exc:
            self.message(f"The repository was not changed:\n{exc}")
            return
        self.show_edit_fields(False)
        self._fill_repo_selector(final_name)
        self.update_new_repo_visibility(final_name)
        # Only the fields the edit changed; formats, templates and other
        # choices made in the dialog but not yet pushed are kept.
        profile = self.store.get(final_name) or {}
        self.repo_path_input.value = profile.get("path", "")
        self.git_url_input.value = profile.get("url", "")
        if self.creds.available:
            self.use_pat_input.value = bool(profile.get("useStoredPat", False))
        self.message("\n".join(["Repository updated."] + notes))

    def remove_selected(self) -> None:
        name = self.selected_repo_name()
        if name == ADD_NEW_OPTION:
            return
        if not self.ask_yes_no(
            f"Remove '{name}' from this add-in?\n\nThis only forgets the saved entry. The local folder, "
            "the GitHub repository and its history are not touched, and you can add it again later."
        ):
            return
        delete_token = False
        has_token = False
        if self.creds.available:
            try:
                has_token = bool(self.creds.get(name))
            except CredentialError as exc:
                if self.logger:
                    self.logger.warning("Couldn't check for a stored token: %s", exc)
        if has_token:
            delete_token = self.ask_yes_no(
                "Also delete the token stored for this repository?\n\n"
                "Choose No to keep it in Windows Credential Manager."
            )
        try:
            _removed, notes = self.controller.remove_profile(name, delete_token=delete_token)
        except (SettingsError, CredentialError, OSError) as exc:
            self.message(f"The repository was not removed:\n{exc}")
            return
        self._fill_repo_selector(None)
        self.auto_path = True
        self.update_new_repo_visibility(ADD_NEW_OPTION)
        self.git_url_input.value = ""
        self.new_repo_name_input.value = ""
        self.ensure_new_repo_defaults()
        done = f"'{name}' was removed from the add-in."
        if delete_token and not notes:
            done += " Its stored token was deleted."
        self.message("\n".join([done] + notes))

    # ------------------------------------------------------------------
    # Input changes
    # ------------------------------------------------------------------

    def on_input_changed(self, changed_input) -> None:
        if not changed_input:
            return
        input_id = changed_input.id
        if input_id == "repoSelector":
            sel = self.repo_selector.selectedItem
            if sel:
                self.update_new_repo_visibility(sel.name)
                if sel.name == ADD_NEW_OPTION:
                    self.auto_path = True
                    self.ensure_new_repo_defaults()
                else:
                    self.apply_repo_settings(sel.name)
                    self.auto_path = False
                    self.update_validation(sel.name)
        elif input_id == "newRepoName":
            self.auto_path = True
            self.ensure_new_repo_defaults()
        elif input_id == "repoPath":
            self.auto_path = False
            self.update_validation()
        elif input_id == "gitUrl":
            self.on_git_url_changed()
        elif input_id == "exportFormatsConfig":
            self.sync_format_settings_rows()
        elif input_id == "branchPreview":
            preview_input = self.inputs.itemById("branchPreview")
            # Blank means "no override" — never sanitize an empty value, because
            # sanitize_branch_name() would fill in its "fusion-export" fallback
            # and silently turn every push into an explicit branch override.
            if preview_input and preview_input.value.strip():
                sanitized = sanitize_branch_name(preview_input.value)
                if sanitized != preview_input.value:
                    preview_input.value = sanitized
        elif input_id == "exportSubfolder":
            export_input = self.inputs.itemById("exportSubfolder")
            normalized_value = self.update_export_subfolder_feedback(export_input.value)
            if normalized_value != export_input.value:
                export_input.value = normalized_value
        elif input_id.startswith("formatSetting_"):
            # Ids carry a per-rebuild generation suffix ("_g<n>").
            row_key = re.sub(r"_g\d+$", "", input_id.split("_", 1)[1])
            data = self.format_setting_inputs.get(row_key)
            if data:
                fmt_key, dropdown, state_key, options = data
                selected = dropdown.selectedItem
                if selected:
                    self.format_settings_state.setdefault(fmt_key, {})[state_key] = dict(options).get(
                        selected.name, selected.name
                    )
        elif input_id in ("browseRepoPath", "editBrowse"):
            changed_input.value = False
            folder_dialog = self.ui.createFolderDialog()
            folder_dialog.title = "Select Repository Folder"
            if folder_dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                if input_id == "browseRepoPath":
                    self.repo_path_input.value = folder_dialog.folder
                    self.auto_path = False
                else:
                    self.edit_path_input.value = folder_dialog.folder
            self.update_validation()
        elif input_id == "logLevel":
            selected_item = self.log_level_dropdown.selectedItem
            if selected_item:
                addin_logging.set_logger_level(selected_item.name)
        elif input_id == "openLogFile":
            changed_input.value = False
            addin_logging.open_log_file(self.ui, self.title)
        elif input_id == "clearLogFile":
            changed_input.value = False
            if self.ask_yes_no("Delete the add-in's log files?"):
                addin_logging.clear_log_files(self.ui, self.title)
        elif input_id == "openPrivacy":
            changed_input.value = False
            addin_logging.open_privacy_policy(self.ui, self.title)
        elif input_id == "patSave":
            changed_input.value = False
            repo_name = self.selected_repo_name()
            if repo_name != ADD_NEW_OPTION:
                self.save_pat_entry(repo_name)
        elif input_id == "managePat":
            changed_input.value = False
            repo_name = self.selected_repo_name()
            if repo_name == ADD_NEW_OPTION:
                self.message("Add the repository before managing credentials.")
            else:
                self.manage_pat_for_repo(repo_name)
        elif input_id == "useStoredPat" and self.creds.available:
            self.on_use_stored_pat_changed()
        elif input_id == "editRepo":
            changed_input.value = False
            self.toggle_edit()
        elif input_id == "saveRepoEdit":
            changed_input.value = False
            self.save_edit()
        elif input_id == "removeRepo":
            changed_input.value = False
            self.remove_selected()

    # ------------------------------------------------------------------
    # OK: set up (if new), export and push
    # ------------------------------------------------------------------

    def ask_identity(self):
        """Ask for the name and email Git records on each commit (decision Q14)."""
        default_name = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        name_val, cancelled = self.ui.inputBox(
            "Git labels every snapshot with a name.\nEnter your name (saved for this repository):",
            self.title,
            default_name,
        )
        if cancelled or not (name_val or "").strip():
            return None
        email_val, cancelled = self.ui.inputBox(
            "Enter your email address (only used to label your snapshots):", self.title, ""
        )
        if cancelled or not (email_val or "").strip():
            return None
        everywhere = self.ask_yes_no(
            "Also use this name and email for all Git repositories on this computer?\n\n"
            "Choose No to use them only for this repository in this add-in."
        )
        return (name_val.strip(), email_val.strip(), everywhere)

    def execute(self, execute_args) -> None:
        """Start the push. Leaves the dialog open (executeFailed) whenever it didn't start.

        Everything up to the push plan (export, questions, settings) happens
        here on Fusion's main thread, so a refusal keeps the dialog open. The
        git part then runs in the background and the dialog closes.
        """
        progress = None
        try:
            if self.logger:
                self.logger.info("Execute handler starting")
            result = self._execute(execute_args)
            if result is False:
                execute_args.executeFailed = True
        except Exception:
            self.message("ExecuteHandler failed:\n{}".format(redact_secrets(traceback.format_exc())))
            if self.logger:
                self.logger.exception("ExecuteHandler failed")
            try:
                execute_args.executeFailed = True
            except Exception:
                pass
        finally:
            progress = getattr(self, "_progress", None)
            if progress:
                try:
                    progress.hide()
                except Exception:
                    pass

    def _fail(self, text: str) -> bool:
        self.message(text)
        if self.logger:
            self.logger.warning(text)
        return False

    def _execute(self, execute_args) -> bool:
        """Return True when the dialog may close, False to keep it open."""
        cmd_inputs = execute_args.command.commandInputs
        selected_item = cmd_inputs.itemById("repoSelector").selectedItem
        if not selected_item:
            self.ui.messageBox("No action or repository selected.")
            return False
        selected_action = selected_item.name
        if push_worker.is_busy() or (self.ctx.bridge is not None and self.ctx.bridge.busy):
            return self._fail(BUSY_TEXT)

        repo_path_raw = cmd_inputs.itemById("repoPath").value.strip()
        git_url_val = ""
        if selected_action == ADD_NEW_OPTION:
            git_url_val = convert_github_url(cmd_inputs.itemById("gitUrl").value.strip())

        validation = validate_repo_inputs(selected_action, repo_path_raw, git_url_val, ADD_NEW_OPTION)
        if not validation["ok"]:
            error_lines = [msg for msg, severity in validation["messages"].values() if severity == "error"]
            if error_lines:
                return self._fail(
                    "⚠️ Please fix these issues:\n\n" + "\n".join(error_lines) + "\n\nDialog will stay open for corrections."
                )
        normalized_repo_path = validation["path"]
        if normalized_repo_path:
            self.repo_path_input.value = normalized_repo_path

        selected_formats = [item.name for item in cmd_inputs.itemById("exportFormatsConfig").listItems if item.isSelected]
        export_formats_val = selected_formats or ["f3d"]
        format_settings = self.collect_format_settings_from_ui()
        format_settings = {fmt: format_settings[fmt] for fmt in export_formats_val if format_settings.get(fmt)}
        default_message_tpl = cmd_inputs.itemById("defaultMessageConfig").value.strip() or DEFAULT_COMMIT_TEMPLATE
        branch_format_tpl = cmd_inputs.itemById("branchFormatConfig").value.strip() or DEFAULT_BRANCH_FORMAT

        if not check_git_available(self.ui, self.logger):
            return False

        if selected_action == ADD_NEW_OPTION:
            name = self._set_up_new_repository(
                cmd_inputs, git_url_val, normalized_repo_path, export_formats_val, format_settings,
                default_message_tpl, branch_format_tpl,
            )
            if name is None:
                return False
            selected_action = name
            normalized_repo_path = self.store.get(name)["path"]

        return self._push_saved_repository(
            cmd_inputs, selected_action, normalized_repo_path, export_formats_val, format_settings,
            default_message_tpl, branch_format_tpl,
        )

    def _set_up_new_repository(
        self, cmd_inputs, git_url, normalized_repo_path, formats, format_settings, message_tpl, branch_tpl
    ) -> Optional[str]:
        repo_name = cmd_inputs.itemById("newRepoName").value.strip()
        if not repo_name and git_url:
            # Name left blank: derive it from the URL, as the quick-setup
            # instructions promise.
            repo_name = derive_repo_name_from_url(git_url)
        if not repo_name:
            self._fail("New repository name cannot be empty.")
            return None
        try:
            repo_name = self.store.check_name(repo_name)
        except SettingsError:
            self._fail("Repository name is reserved for internal use.")
            return None
        # The auto path tracks the repo name, which may have just been derived.
        local_path = resolve_new_repo_path(repo_name, normalized_repo_path, self.auto_path, self.ctx.repo_base_dir, _safe_base)

        existing = self.store.get(repo_name)
        if existing is not None:
            stored = os.path.normcase(os.path.normpath(os.path.expanduser(existing.get("path") or "")))
            same_repo = stored == os.path.normcase(os.path.normpath(local_path)) and (existing.get("url") or "") == (
                git_url or ""
            )
            if not same_repo:
                self._fail(
                    f"Repo '{repo_name}' already exists with a different URL or folder. Pick a different "
                    "name, or select the saved repository from the dropdown instead."
                )
                return None
            # Same name, URL and folder: a re-submit of the same setup (e.g. a
            # retry after a failed push while the dialog stayed open).

        parent_dir = os.path.dirname(local_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        error = setup_new_repository(repo_name, local_path, git_url, git_run, logger=self.logger, confirm=self.git_ui.confirm)
        if error:
            self._fail(error)
            return None

        profile = {
            "url": git_url,
            "path": local_path.replace("/", os.sep),
            "exportFormats": formats,
            "formatSettings": format_settings,
            "defaultMessage": message_tpl,
            "branchFormat": branch_tpl,
        }
        try:
            if existing is None:
                self.store.add(repo_name, profile)
            else:
                self.store.update(repo_name, profile)
        except SettingsError as exc:
            self._fail(str(exc))
            return None
        self.meta["lastSelectedRepo"] = repo_name
        self.meta.setdefault("lastCommitMessage", "Updated design")
        self.save_settings()

        # The push must use the folder the repository was just set up in, not
        # the path validated before the name was known (BUG-01).
        normalized_repo_path = local_path
        self.repo_path_input.value = normalized_repo_path
        if self.logger:
            self.logger.info("Repository '%s' added (%s). Continuing to push...", repo_name, git_url)
        return repo_name

    def _push_saved_repository(
        self, cmd_inputs, repo_name, normalized_repo_path, formats, format_settings, message_tpl, branch_tpl
    ) -> bool:
        profile = self.store.get(repo_name)
        if profile is None:
            return self._fail(f"Error: Selected repo '{repo_name}' not found in config.")

        commit_msg = cmd_inputs.itemById("commitMsgPush").value.strip() or message_tpl
        try:
            export_subfolder = normalize_export_subfolder(cmd_inputs.itemById("exportSubfolder").value)
        except ValueError as exc:
            return self._fail(str(exc))

        branch_preview_input = cmd_inputs.itemById("branchPreview")
        override_raw = branch_preview_input.value.strip()
        override = sanitize_branch_name(override_raw) if override_raw else ""
        if override_raw and not override:
            return self._fail("Branch name contains unsupported characters even after sanitization.")
        if override:
            branch_preview_input.value = override

        selected_log = self.log_level_dropdown.selectedItem
        log_level = selected_log.name if selected_log else addin_logging.current_log_level_name
        addin_logging.set_logger_level(log_level)

        changes = {
            "path": normalized_repo_path or profile.get("path", ""),
            "exportFormats": formats,
            "formatSettings": format_settings,
            "defaultMessage": message_tpl,
            "branchFormat": branch_tpl,
            "exportSubfolder": export_subfolder,
            "logLevel": log_level,
        }
        if self.creds.available:
            changes["useStoredPat"] = bool(cmd_inputs.itemById("useStoredPat").value)
        try:
            self.store.update(repo_name, changes)
        except SettingsError as exc:
            return self._fail(str(exc))
        self.meta["lastSelectedRepo"] = repo_name
        self.meta["lastCommitMessage"] = commit_msg
        self.meta["globalLogLevel"] = log_level
        if not self.save_settings():
            return False

        design = get_fusion_design(self.ctx.app, self.logger)
        if not design:
            return self._fail("No active Fusion design.")
        design_name, design_id = design_identity(design)

        repo_path = os.path.expanduser(self.store.get(repo_name)["path"]).replace("/", os.sep)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return self._fail(f"Path '{repo_path}' for repo '{repo_name}' is not a Git repo.")

        export_warnings: List[str] = []
        # The exports must outlive this method when the push goes to the
        # background: the stack is handed to the worker, which removes them.
        with contextlib.ExitStack() as export_files:
            temp_dir = export_files.enter_context(temporary_export_dir())
            self._progress = progress = self.ui.createProgressDialog()
            progress.isBackgroundTranslucencyEnabled = True
            progress.cancelButtonText = ""
            progress.show("Fusion → GitHub", "Exporting design…", 0, 2, 0)
            valid_formats, warnings = determine_valid_export_formats(design, formats)
            export_warnings.extend(warnings)
            if not valid_formats:
                progress.hide()
                return self._fail("No valid export formats available for this design.")
            export = export_design(
                design, temp_dir, design_name, valid_formats,
                {fmt: format_settings.get(fmt, {}) for fmt in valid_formats}, self.logger,
            )
            progress.hide()
            export_warnings.extend(export.warnings)
            if not export.ok:
                # All or nothing: a partial backup is never pushed, and
                # HISTORY.md is not touched.
                problems = export.failures or ["No files were exported."]
                return self._fail(
                    "Nothing was pushed because these exports failed:\n"
                    + "\n".join(f" • {problem}" for problem in problems)
                )
            exported = export.files
            history_notes: List[str] = []
            if export.linked_components:
                if not self.ask_yes_no(linked_components_question(export.linked_components)):
                    self.message("Push cancelled — nothing was pushed.")
                    return False
                history_notes.append(linked_components_note(export.linked_components))

            # Questions (publication notice, identity) come with the progress
            # dialog hidden, so they can't end up behind it.
            request = PushRequest(
                profile_name=repo_name, design_name=design_name, design_id=design_id,
                commit_message=commit_msg, branch_override=override,
                history_notes=history_notes,
            )
            try:
                plan = self.controller.plan(request, exported, confirm=self.git_ui.confirm, ask_identity=self.ask_identity)
            except PushCancelled:
                self.message(NOTHING_PUSHED)
                return False
            except PushRefused as exc:
                return self._fail(str(exc))
            except (SettingsError, ValueError, OSError, CredentialError, GitError) as exc:
                return self._fail(f"Push not started:\n{redact_secrets(str(exc))}")

            # Asked here, on the main thread, so the background push doesn't.
            size_error, size_question = export_size_check(plan.exports)
            if size_error:
                return self._fail(size_error)
            if size_question:
                if not self.ask_yes_no(size_question):
                    self.message(NOTHING_PUSHED)
                    return False
                plan.large_files_confirmed = True

            return self._start_background_push(plan, repo_name, export_warnings, export_files)

    def _start_background_push(self, plan, repo_name, export_warnings, export_files) -> bool:
        """Hand the plan to the worker; True (the dialog closes) once it is running."""
        bridge = self.ctx.bridge
        if bridge is None:
            return self._fail("The add-in's background push isn't available. Restart the add-in and try again.")
        job = PushJob(
            repo_name=repo_name,
            exported_names=[rel for _, rel in plan.exports],
            warnings=list(export_warnings) + list(plan.notes),
        )
        cleanup = export_files.pop_all()  # from now on the worker owns the exported files
        try:
            bridge.start(self.controller, plan, job, on_finish=cleanup.close)
        except WorkerBusy:
            cleanup.close()
            return self._fail(BUSY_TEXT)
        except RuntimeError as exc:
            cleanup.close()
            return self._fail(str(exc))
        if self.logger:
            self.logger.info("Push of '%s' to '%s' started in the background", plan.design_name, repo_name)
        return True


# ----------------------------------------------------------------------
# Fusion event handlers (thin wrappers)
# ----------------------------------------------------------------------


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self, dialog: PushDialog):
        super().__init__()
        self.dialog = dialog

    def notify(self, args):
        # Exceptions escaping an event handler crash the dialog silently.
        try:
            self.dialog.on_input_changed(args.input)
        except Exception:
            if self.dialog.logger:
                self.dialog.logger.exception("InputChangedHandler failed")


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, dialog: PushDialog):
        super().__init__()
        self.dialog = dialog

    def notify(self, args):
        try:
            self.dialog.execute(args)
        except Exception:
            if self.dialog.logger:
                self.dialog.logger.exception("ExecuteHandler failed")


def open_dialog(ctx: DialogContext, command) -> PushDialog:
    """Build a dialog on *command* and register its handlers (kept alive in ctx.handlers)."""
    dialog = PushDialog(ctx, command)
    dialog.build()
    on_input_changed = InputChangedHandler(dialog)
    command.inputChanged.add(on_input_changed)
    on_execute = ExecuteHandler(dialog)
    command.execute.add(on_execute)
    ctx.handlers.extend([on_input_changed, on_execute])
    dialog.show_load_messages()
    return dialog


__all__ = ["ADD_NEW_OPTION", "DialogContext", "FusionCommandGitUI", "PushDialog", "open_dialog", "check_git_available"]
