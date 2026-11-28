"""The "Push to GitHub" command dialog.

``PushDialog`` owns the dialog's inputs and state. The Fusion event-handler
classes at the bottom are thin wrappers: they call a ``PushDialog`` method
and never let an exception escape (an exception escaping a Fusion handler
silently breaks the dialog).

Layout (audit UX-06): the basic view holds only what a backup needs — the
design, the repository, "What changed?" and the files to include — and
says where the backup will go. Git details (history mode, branches,
templates, the stored token) are under Advanced; logs and the privacy
policy under Help & Privacy. OK ("Back up now") stays disabled until the
inputs are valid (``validate``, audit UX-02), and no message box ever shows
a Python traceback (``error_catalog``, audit UX-04).

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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import adsk.core
import adsk.fusion  # noqa: F401  (Design type checks happen in fusion_export)

from . import addin_logging, error_catalog, push_worker, setup_check
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
from .fusion_bridge import BUSY_TEXT, NOTHING_PUSHED, PushJob, WorkerBusy
from .fusion_export import (
    AVAILABLE_FORMATS,
    DEFAULT_FORMATS,
    FORMAT_CHOICE_LABELS,
    FORMAT_SETTING_LABELS,
    FORMAT_SETTINGS_DEFAULT,
    FORMAT_SETTINGS_OPTIONS,
    _safe_base,
    design_identity,
    design_version_text,
    determine_valid_export_formats,
    export_design,
    format_from_choice,
    get_fusion_design,
    linked_components_note,
    linked_components_question,
    temporary_export_dir,
)
from .fusion_git_core import (
    MODE_SINGLE,
    MODE_SNAPSHOT,
    GitError,
    branch_name_problem,
    export_size_check,
    git_available,
    git_run,
    redact_secrets,
    sanitize_branch_name,
)
from .push_controller import (
    DEFAULT_BRANCH_FORMAT,
    DEFAULT_COMMIT_TEMPLATE,
    NEW_PROFILE_SUBFOLDER,
    PushCancelled,
    PushController,
    PushRefused,
    PushRequest,
    new_profile_settings,
)
from .settings_store import SettingsError, SettingsStore, history_mode

ADD_NEW_OPTION = "Set up a new GitHub repository…"
DIALOG_TITLE_CONFIG_ERROR = "Settings problem"
DIALOG_TITLE_GIT_NOT_FOUND = "Git not found"
OK_BUTTON_TEXT = "Back up now"
COMMIT_PROMPT = "What changed?"


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
            self._ui.messageBox(error_catalog.explain(message), self._title)

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
    check = setup_check.check_git()
    msg = setup_check.format_report([check], heading="Git is needed to back up to GitHub.")
    target_ui_ref.messageBox(msg, DIALOG_TITLE_GIT_NOT_FOUND)
    if logger:
        logger.error("Git executable not found or not working.")
    return False


def _strip_marks(text: str) -> str:
    """A validation message without its leading symbol (✅, ❌, ⚠️, ℹ️)."""
    return re.sub(r"^[^\w(\"']+\s*", "", text or "").strip()


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
        self.design = get_fusion_design(ctx.app, self.logger)

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
            self.message(f"Your settings couldn't be saved:\n{exc}", DIALOG_TITLE_CONFIG_ERROR)
            if self.logger:
                self.logger.error("Settings save failed: %s", exc)
            return False

    @property
    def meta(self) -> Dict[str, Any]:
        return self.store.meta

    def selected_repo_name(self) -> str:
        sel = self.repo_selector.selectedItem
        return sel.name if sel else ADD_NEW_OPTION

    def value(self, input_id: str, default: Any = "") -> Any:
        found = self.inputs.itemById(input_id)
        return found.value if found is not None else default

    # ------------------------------------------------------------------
    # Building the dialog
    # ------------------------------------------------------------------

    def build(self) -> None:
        cmd = self.command
        cmd.isAutoExecute = False
        cmd.isAutoTerminate = True
        try:
            cmd.okButtonText = OK_BUTTON_TEXT
        except Exception:
            if self.logger:
                self.logger.debug("This Fusion version can't rename the OK button.")
        inputs = self.inputs = cmd.commandInputs
        meta = self.meta

        self.design_status_input = inputs.addTextBoxCommandInput("designStatus", "Design", self.design_status(), 2, True)

        repo_group = inputs.addGroupCommandInput("repoGroup", "Repository")
        repo_group.isExpanded = True
        repo_inputs = self.repo_inputs = repo_group.children

        self.repo_selector = repo_inputs.addDropDownCommandInput(
            "repoSelector", "Repository", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        self.repo_selector.tooltip = "The GitHub repository this design is backed up to."
        self._fill_repo_selector(meta.get("lastSelectedRepo"))

        self.git_url_input = repo_inputs.addStringValueInput("gitUrl", "GitHub address", "")
        self.git_url_input.tooltip = (
            "Paste the repository's address from your browser, for example https://github.com/you/designs. "
            "Create the repository on github.com first; a private one is best for designs you don't want to publish."
        )
        self.new_repo_name_input = repo_inputs.addStringValueInput("newRepoName", "Name in this list", "")
        self.new_repo_name_input.tooltip = "Optional. How this repository is listed here; taken from the address if blank."
        self.repo_path_input = repo_inputs.addStringValueInput("repoPath", "Local folder", "")
        self.repo_path_input.tooltip = "Where Git keeps its copy of the repository on this computer."
        self.browse_repo_button = repo_inputs.addBoolValueInput("browseRepoPath", "Choose folder…", False, "", False)
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
            "First backup: 1) create a repository on github.com (private is best), 2) paste its address above, "
            "3) describe what changed and click Back up now. Check My Setup tests everything first.",
            3,
            True,
        )
        self.help_text_input.isFullWidth = True

        self.destination_input = repo_inputs.addTextBoxCommandInput("destinationText", "Saves to", "", 2, True)

        # Edit / Remove a saved repository.
        self.edit_repo_button = repo_inputs.addBoolValueInput("editRepo", "Edit Repository…", False, "", False)
        self.edit_repo_button.isFullWidth = True
        self.remove_repo_button = repo_inputs.addBoolValueInput("removeRepo", "Remove Repository…", False, "", False)
        self.remove_repo_button.isFullWidth = True
        self.remove_repo_button.tooltip = (
            "Forget this saved repository. The local folder, the GitHub repository and its "
            "history are not touched."
        )
        self.edit_name_input = repo_inputs.addStringValueInput("editRepoName", "Name in this list", "")
        self.edit_url_input = repo_inputs.addStringValueInput("editGitUrl", "GitHub address", "")
        self.edit_path_input = repo_inputs.addStringValueInput("editRepoPath", "Local folder", "")
        self.edit_browse_button = repo_inputs.addBoolValueInput("editBrowse", "Choose folder…", False, "", False)
        self.edit_save_button = repo_inputs.addBoolValueInput("saveRepoEdit", "Save Changes", False, "", False)
        self.edit_save_button.isFullWidth = True
        self.edit_inputs = [
            self.edit_name_input, self.edit_url_input, self.edit_path_input,
            self.edit_browse_button, self.edit_save_button,
        ]
        check_button = repo_inputs.addBoolValueInput("checkSetup", "Check My Setup…", False, "", False)
        check_button.isFullWidth = True
        check_button.tooltip = "Check Git, your GitHub sign-in and this repository, without backing anything up."

        current_selection = self.selected_repo_name()
        self.update_new_repo_visibility(current_selection)

        # What changed: required, empty every time (audit UX-10).
        self.commit_input = inputs.addStringValueInput("commitMsgPush", COMMIT_PROMPT, "")
        self.commit_input.tooltip = (
            "Required. A few words about this version, for example 'holes widened to 5 mm'. "
            "It is shown in the design's history on GitHub."
        )

        export_group = inputs.addGroupCommandInput("exportGroup", "Files to include")
        export_group.isExpanded = current_selection == ADD_NEW_OPTION
        self.export_inputs = export_group.children
        self.export_formats_dropdown = self.export_inputs.addDropDownCommandInput(
            "exportFormatsConfig", "Files", adsk.core.DropDownStyles.CheckBoxDropDownStyle
        )
        self.export_formats_dropdown.tooltip = "Choose one or more. The Fusion design file is the one to restore from."
        for fmt in AVAILABLE_FORMATS:
            self.export_formats_dropdown.listItems.add(FORMAT_CHOICE_LABELS[fmt], fmt in DEFAULT_FORMATS, "")

        # addTableCommandInput's signature differs across Fusion API
        # versions: try the 4-arg form, then the 3-arg form, otherwise run
        # without the settings table (defaults still apply).
        try:
            self.format_settings_table = self.export_inputs.addTableCommandInput(
                "formatSettingsTable", "Format settings", 2, "1:1"
            )
        except Exception:
            try:
                self.format_settings_table = self.export_inputs.addTableCommandInput(
                    "formatSettingsTable", "Format settings", 2
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

        self.summary_input = inputs.addTextBoxCommandInput("validationSummary", "", "", 2, True)
        self.summary_input.isFullWidth = True

        # Advanced: how the backup is recorded in Git, and the stored token.
        flow_group = inputs.addGroupCommandInput("flowGroup", "Advanced")
        flow_group.isExpanded = False
        flow_inputs = flow_group.children
        self.snapshot_input = flow_inputs.addBoolValueInput(
            "snapshotMode", "Separate branch per backup", True, "", False
        )
        self.snapshot_input.tooltip = (
            "Off (recommended): every backup is added to one running history, so the design's folder on "
            "GitHub always shows the latest version and its history lists every backup.\n"
            "On: each backup goes to a new branch of its own (the way versions before 0.7.0 worked)."
        )
        target_input = flow_inputs.addStringValueInput("targetBranch", "Backup branch", "")
        target_input.tooltip = (
            "Leave blank to add backups to the repository's main branch. Enter a name (for example "
            "fusion-backups) to keep them on a branch of their own; it is created on the first backup."
        )
        branch_template = flow_inputs.addStringValueInput("branchFormatConfig", "Branch name template", DEFAULT_BRANCH_FORMAT)
        branch_template.tooltip = (
            "For separate branches: the name of each new branch. {filename} is the design's name, "
            "{timestamp} the date and time of the backup."
        )
        branch_override_input = flow_inputs.addStringValueInput("branchPreview", "Use this branch instead", "")
        branch_override_input.tooltip = (
            "For separate branches, this backup only: push to this branch instead of a new one "
            "(adding to it if it already exists)."
        )
        subfolder_input = flow_inputs.addStringValueInput("exportSubfolder", "Design folders go in", NEW_PROFILE_SUBFOLDER)
        subfolder_input.tooltip = (
            "The folder in the repository that holds one folder per design, for example 'designs'. "
            "Blank puts the design folders at the top level. {filename} and {timestamp} may be used."
        )
        message_template = flow_inputs.addStringValueInput("defaultMessageConfig", "Commit message format", DEFAULT_COMMIT_TEMPLATE)
        message_template.tooltip = (
            "How each commit is titled. {message} is what you typed in What changed?, {filename} the "
            "design's name, {timestamp} the date and time."
        )
        tokens_supported = bool(getattr(self.creds, "available", False))
        self.use_pat_input = flow_inputs.addBoolValueInput("useStoredPat", "Use stored token", True, "", False)
        self.use_pat_input.isFullWidth = False
        self.use_pat_input.isVisible = tokens_supported
        self.use_pat_input.tooltip = (
            "Sign in to GitHub with a token stored in Windows Credential Manager instead of the "
            "Git Credential Manager window."
        )
        self.manage_pat_button = flow_inputs.addBoolValueInput("managePat", "Manage Token…", False, "", False)
        self.manage_pat_button.isFullWidth = True
        self.manage_pat_button.isVisible = tokens_supported

        # Token entry, shown by "Manage Token…". The token field is a
        # password field, so the token is never visible on screen (audit
        # SEC-07); it is cleared as soon as it has been saved.
        self.pat_username_input = flow_inputs.addStringValueInput("patUsername", "Token username", "")
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

        log_group = inputs.addGroupCommandInput("logGroup", "Help & Privacy")
        log_group.isExpanded = False
        log_inputs = log_group.children
        privacy_button = log_inputs.addBoolValueInput("openPrivacy", "Privacy Policy…", False, "", False)
        privacy_button.isFullWidth = True
        privacy_button.tooltip = "What this add-in stores and sends, and how to delete it."
        open_log_button = log_inputs.addBoolValueInput("openLogFile", "Open Log File…", False, "", False)
        open_log_button.isFullWidth = True
        clear_log_button = log_inputs.addBoolValueInput("clearLogFile", "Clear Log", False, "", False)
        clear_log_button.isFullWidth = True
        clear_log_button.tooltip = (
            "Delete the add-in's log files. They contain folder paths, repository addresses and Git messages."
        )
        self.log_level_dropdown = log_inputs.addDropDownCommandInput(
            "logLevel", "Log detail", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        for level_name in ["ERROR", "WARNING", "INFO", "DEBUG"]:
            self.log_level_dropdown.listItems.add(level_name, level_name == addin_logging.current_log_level_name, "")

        self.sync_format_settings_rows()
        if current_selection != ADD_NEW_OPTION:
            self.apply_repo_settings(current_selection)
        self.ensure_new_repo_defaults()
        self.update_mode_visibility()
        self.update_destination()
        self.refresh_summary()

    def design_status(self) -> str:
        if not self.design:
            return "No design is open. Open the design you want to back up, then click Push to GitHub again."
        name, _ = design_identity(self.design)
        version = design_version_text(self.design)
        text = f"{name} (Fusion version: {version})" if version else name
        if "unsaved" in version or version == "not saved yet":
            text += (
                "\nThe backup includes unsaved changes, but Fusion's own version history doesn't "
                "until you save."
            )
        return text

    def show_load_messages(self) -> None:
        """Explain, once, anything unusual that happened while loading settings."""
        if self.load_report.messages:
            self.message("\n\n".join(self.load_report.messages), DIALOG_TITLE_CONFIG_ERROR)
            for text in self.load_report.messages:
                if self.logger:
                    self.logger.warning("Settings: %s", text)

    def show_first_run_checks(self) -> None:
        """No saved repository yet: report anything that would stop a first backup (audit UX-07)."""
        if self.store.profile_names():
            return
        checks = setup_check.local_checks(None, None)
        if setup_check.has_problem(checks):
            self.message(setup_check.format_report(checks, heading="Before your first backup"))

    def _fill_repo_selector(self, preferred: Optional[str]) -> None:
        """(Re)fill the repository dropdown, selecting *preferred* when it exists."""
        names = self.store.profile_names()
        items = self.repo_selector.listItems
        items.clear()
        selected = preferred if preferred in names else (names[0] if names else ADD_NEW_OPTION)
        for name in names + [ADD_NEW_OPTION]:
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

    def update_mode_visibility(self) -> None:
        snapshot = bool(self.snapshot_input.value)
        self.inputs.itemById("targetBranch").isVisible = not snapshot
        self.inputs.itemById("branchFormatConfig").isVisible = snapshot
        self.inputs.itemById("branchPreview").isVisible = snapshot

    def current_mode(self) -> str:
        return MODE_SNAPSHOT if self.snapshot_input.value else MODE_SINGLE

    def update_destination(self) -> None:
        """Say where the backup will go (audit UX-01, risk R-20): branch › folder."""
        folder_parent = ""
        try:
            folder_parent = normalize_export_subfolder(self.value("exportSubfolder"))
        except ValueError:
            pass
        design_name = design_identity(self.design)[0] if self.design else "<design>"
        folder = f"{folder_parent}/{design_name}/" if folder_parent and "{filename}" not in folder_parent else (
            f"{folder_parent}/" if folder_parent else f"{design_name}/")
        if self.current_mode() == MODE_SNAPSHOT:
            where = f"a new branch for each backup › {folder}"
        else:
            branch = self.value("targetBranch").strip() or "the repository's main branch"
            where = f"{branch} › {folder}"
        self.destination_input.text = where

    # ------------------------------------------------------------------
    # Validation (audit UX-02): OK stays disabled until this is empty
    # ------------------------------------------------------------------

    def validation_problems(self) -> List[str]:
        problems: List[str] = []
        if not self.design:
            problems.append("Open a Fusion design first.")
        selection = self.selected_repo_name()
        if selection == ADD_NEW_OPTION:
            validation = self.update_validation(selection)
            problems += [_strip_marks(msg) for msg, severity in validation["messages"].values() if severity == "error"]
            if not self.git_url_input.value.strip():
                problems.append("Paste the GitHub address of the repository to back up to.")
        if not (self.commit_input.value or "").strip():
            problems.append(f"Describe what changed ({COMMIT_PROMPT}).")
        if not self.get_selected_formats():
            problems.append("Choose at least one file to include.")
        try:
            normalize_export_subfolder(self.value("exportSubfolder"))
        except ValueError as exc:
            problems.append(f"Advanced → Design folders go in: {exc}")
        if self.current_mode() == MODE_SINGLE:
            target = self.value("targetBranch").strip()
            if target and branch_name_problem(target):
                problems.append(f"Advanced → Backup branch: {branch_name_problem(target)}")
        return list(dict.fromkeys(p for p in problems if p))

    def refresh_summary(self) -> List[str]:
        problems = self.validation_problems()
        self.summary_input.text = ("Before backing up: " + " ".join(problems)) if problems else ""
        return problems

    def validate(self, args) -> None:
        args.areInputsValid = not self.refresh_summary()

    # ------------------------------------------------------------------
    # Export format settings table
    # ------------------------------------------------------------------

    def get_selected_formats(self) -> List[str]:
        return [format_from_choice(item.name) for item in self.export_formats_dropdown.listItems if item.isSelected]

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
        table.isVisible = row_index > 1

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
            self.flow_status_input.text = ""
            return normalized
        except ValueError as exc:
            self.flow_status_input.text = f"Design folders go in: {exc}"
            return raw_value

    # ------------------------------------------------------------------
    # Repository selection and validation
    # ------------------------------------------------------------------

    def apply_repo_settings(self, repo_name: str) -> None:
        det = self.store.get(repo_name) or {}
        inputs = self.inputs
        saved_formats = set(det.get("exportFormats", []))
        for item in self.export_formats_dropdown.listItems:
            code = format_from_choice(item.name)
            item.isSelected = code in saved_formats if saved_formats else code in DEFAULT_FORMATS

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
        self.snapshot_input.value = history_mode(det) == MODE_SNAPSHOT
        inputs.itemById("targetBranch").value = det.get("targetBranch", "") or ""

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
        self.update_mode_visibility()

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

    def update_auto_path(self) -> None:
        """While the folder is still the suggested one, follow the name (or the address's name)."""
        if self.selected_repo_name() == ADD_NEW_OPTION and self.auto_path:
            self.repo_path_input.value = default_path_for_new_repo(
                self.new_repo_name_input.value.strip()
                or derive_repo_name_from_url(convert_github_url(self.git_url_input.value.strip())),
                self.ctx.repo_base_dir, _safe_base
            )

    def ensure_new_repo_defaults(self) -> None:
        """Reset the dialog to a new repository's starting settings."""
        if self.selected_repo_name() == ADD_NEW_OPTION:
            self.update_auto_path()
            self.format_settings_state.clear()
            self.sync_format_settings_rows()
            defaults = new_profile_settings()
            self.inputs.itemById("exportSubfolder").value = defaults["exportSubfolder"]
            self.inputs.itemById("defaultMessageConfig").value = defaults["defaultMessage"]
            self.inputs.itemById("branchFormatConfig").value = defaults["branchFormat"]
            self.inputs.itemById("targetBranch").value = defaults["targetBranch"]
            self.snapshot_input.value = defaults["historyMode"] == MODE_SNAPSHOT
            if self.creds.available:
                self.use_pat_input.value = False
            self.inputs.itemById("branchPreview").value = ""
            self.flow_status_input.text = ""
            level = self.meta.get("globalLogLevel") or addin_logging.current_log_level_name
            for item in self.log_level_dropdown.listItems:
                item.isSelected = item.name == level
            self.update_mode_visibility()
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
                hints.append(f"Will use: {converted}")
            derived_name = derive_repo_name_from_url(converted)
            if derived_name and not self.new_repo_name_input.value.strip():
                hints.append(f"Listed here as: {derived_name}")
        self.conversion_status_input.text = "\n".join(hints)
        self.update_auto_path()
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
            self.message("Stored tokens are only available on Windows.")
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
            self.message("Set up the repository first (back up once), then store a token for it.")
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
    # Check My Setup (audit UX-07)
    # ------------------------------------------------------------------

    def run_setup_check(self) -> None:
        name = self.selected_repo_name()
        profile = self.store.get(name) if name != ADD_NEW_OPTION else None
        token_stored, token_problem, pat = False, "", None
        repo_path = os.path.expanduser((profile or {}).get("path", ""))
        if profile and profile.get("useStoredPat") and self.creds.available:
            try:
                token_stored = bool(self.creds.get(name))
            except CredentialError as exc:
                token_problem = f"Windows Credential Manager couldn't be read: {exc}"
            if token_stored and os.path.isdir(os.path.join(repo_path, ".git")):
                try:
                    pat = self.controller._token_for(name, repo_path)
                except PushRefused as exc:
                    token_problem = str(exc)
        checks = setup_check.local_checks(name if profile else None, profile, token_stored=token_stored,
                                          token_problem=token_problem)
        bridge = self.ctx.bridge
        reason = ""
        if profile is None:
            reason = "Set up the repository (your first backup does that) to test the connection to GitHub."
        elif not setup_check.can_test_connection(checks):
            reason = "Fix the problems above, then check again to test the connection to GitHub."
        elif bridge is None or push_worker.is_busy() or bridge.busy:
            reason = "The connection test can't run while a backup is running. Try again when it has finished."
        if reason:
            checks.append(setup_check.Check(setup_check.INFO, "The connection to GitHub wasn't tested.", reason))
            self.message(setup_check.format_report(checks))
            return
        job = PushJob(repo_name=name, kind="setup_check", checks=[c.as_dict() for c in checks])
        try:
            bridge.start(setup_check.ConnectionTest(repo_path, pat), None, job)
        except (WorkerBusy, RuntimeError) as exc:
            checks.append(setup_check.Check(setup_check.INFO, "The connection to GitHub wasn't tested.", str(exc)))
            self.message(setup_check.format_report(checks))

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
        selection = self.selected_repo_name()
        self.update_new_repo_visibility(selection)
        if selection == ADD_NEW_OPTION:
            self.auto_path = True
            self.git_url_input.value = ""
            self.new_repo_name_input.value = ""
            self.ensure_new_repo_defaults()
        else:
            self.apply_repo_settings(selection)
            self.auto_path = False
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
        self._handle_input(changed_input)
        self.update_destination()
        self.refresh_summary()

    def _handle_input(self, changed_input) -> None:
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
            self.update_auto_path()
            self.update_validation()
        elif input_id == "repoPath":
            self.auto_path = False
            self.update_validation()
        elif input_id == "gitUrl":
            self.on_git_url_changed()
        elif input_id == "exportFormatsConfig":
            self.sync_format_settings_rows()
        elif input_id == "snapshotMode":
            self.update_mode_visibility()
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
            folder_dialog.title = "Choose the repository's local folder"
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
        elif input_id == "checkSetup":
            changed_input.value = False
            self.run_setup_check()
        elif input_id == "patSave":
            changed_input.value = False
            repo_name = self.selected_repo_name()
            if repo_name != ADD_NEW_OPTION:
                self.save_pat_entry(repo_name)
        elif input_id == "managePat":
            changed_input.value = False
            repo_name = self.selected_repo_name()
            if repo_name == ADD_NEW_OPTION:
                self.message("Set up the repository first (back up once), then store a token for it.")
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
            "Git labels every backup with a name.\nEnter your name (saved for this repository):",
            self.title,
            default_name,
        )
        if cancelled or not (name_val or "").strip():
            return None
        email_val, cancelled = self.ui.inputBox(
            "Enter your email address (only used to label your backups; a GitHub 'noreply' address works):",
            self.title, ""
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
        try:
            if self.logger:
                self.logger.info("Execute handler starting")
            result = self._execute(execute_args)
            if result is False:
                execute_args.executeFailed = True
        except Exception as exc:
            # The traceback goes to the log only, never into a dialog (UX-04).
            if self.logger:
                self.logger.exception("ExecuteHandler failed")
            self.message(error_catalog.unexpected_error("starting the backup", exc))
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
            return self._fail("Choose a repository first.")
        selected_action = selected_item.name
        if push_worker.is_busy() or (self.ctx.bridge is not None and self.ctx.bridge.busy):
            return self._fail(BUSY_TEXT)

        # OK is disabled while these fail (validate); checked again here.
        problems = self.validation_problems()
        if problems:
            return self._fail("Please fix these issues:\n\n" + "\n".join(f" • {p}" for p in problems))

        repo_path_raw = cmd_inputs.itemById("repoPath").value.strip()
        git_url_val = ""
        if selected_action == ADD_NEW_OPTION:
            git_url_val = convert_github_url(cmd_inputs.itemById("gitUrl").value.strip())

        validation = validate_repo_inputs(selected_action, repo_path_raw, git_url_val, ADD_NEW_OPTION)
        normalized_repo_path = validation["path"]
        if normalized_repo_path:
            self.repo_path_input.value = normalized_repo_path

        export_formats_val = self.get_selected_formats()
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

    def _history_settings(self, cmd_inputs) -> Dict[str, Any]:
        return {
            "historyMode": self.current_mode(),
            "targetBranch": cmd_inputs.itemById("targetBranch").value.strip(),
        }

    def _set_up_new_repository(
        self, cmd_inputs, git_url, normalized_repo_path, formats, format_settings, message_tpl, branch_tpl
    ) -> Optional[str]:
        repo_name = cmd_inputs.itemById("newRepoName").value.strip()
        if not repo_name and git_url:
            # Name left blank: derive it from the URL, as the quick-setup
            # instructions promise.
            repo_name = derive_repo_name_from_url(git_url)
        if not repo_name:
            self._fail("Give the repository a name for this list.")
            return None
        try:
            repo_name = self.store.check_name(repo_name)
        except SettingsError as exc:
            self._fail(str(exc))
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
                    f"'{repo_name}' is already in the list with a different address or folder. Choose a "
                    "different name, or pick the saved repository from the list instead."
                )
                return None
            # Same name, URL and folder: a re-submit of the same setup (e.g. a
            # retry after a failed push while the dialog stayed open).

        parent_dir = os.path.dirname(local_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        error = setup_new_repository(repo_name, local_path, git_url, git_run, logger=self.logger, confirm=self.git_ui.confirm)
        if error:
            self._fail(error_catalog.explain(redact_secrets(error), nothing_changed=True))
            return None

        profile = new_profile_settings()
        profile.update(self._history_settings(cmd_inputs))
        profile.update({
            "url": git_url,
            "path": local_path.replace("/", os.sep),
            "exportFormats": formats,
            "formatSettings": format_settings,
            "defaultMessage": message_tpl,
            "branchFormat": branch_tpl,
            "exportSubfolder": normalize_export_subfolder(cmd_inputs.itemById("exportSubfolder").value),
        })
        try:
            if existing is None:
                self.store.add(repo_name, profile)
            else:
                self.store.update(repo_name, profile)
        except SettingsError as exc:
            self._fail(str(exc))
            return None
        self.meta["lastSelectedRepo"] = repo_name
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
            return self._fail(f"The saved repository '{repo_name}' no longer exists.")

        commit_msg = cmd_inputs.itemById("commitMsgPush").value.strip()
        if not commit_msg:
            return self._fail(f"Describe what changed ({COMMIT_PROMPT}) first.")
        try:
            export_subfolder = normalize_export_subfolder(cmd_inputs.itemById("exportSubfolder").value)
        except ValueError as exc:
            return self._fail(str(exc))

        override = ""
        if self.current_mode() == MODE_SNAPSHOT:
            branch_preview_input = cmd_inputs.itemById("branchPreview")
            override_raw = branch_preview_input.value.strip()
            override = sanitize_branch_name(override_raw) if override_raw else ""
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
        changes.update(self._history_settings(cmd_inputs))
        if self.creds.available:
            changes["useStoredPat"] = bool(cmd_inputs.itemById("useStoredPat").value)
        try:
            self.store.update(repo_name, changes)
        except SettingsError as exc:
            return self._fail(str(exc))
        self.meta["lastSelectedRepo"] = repo_name
        self.meta.pop("lastCommitMessage", None)  # no longer pre-filled (UX-10)
        self.meta["globalLogLevel"] = log_level
        if not self.save_settings():
            return False

        design = get_fusion_design(self.ctx.app, self.logger)
        if not design:
            return self._fail("No Fusion design is open. Open the design to back up, then try again.")
        design_name, design_id = design_identity(design)
        fusion_version = design_version_text(design)

        repo_path = os.path.expanduser(self.store.get(repo_name)["path"]).replace("/", os.sep)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return self._fail(
                f"The local folder for '{repo_name}' isn't a Git repository folder:\n{repo_path}\n\n"
                "Choose its folder with Edit Repository…, or use Check My Setup."
            )

        export_warnings: List[str] = []
        # The exports must outlive this method when the push goes to the
        # background: the stack is handed to the worker, which removes them.
        with contextlib.ExitStack() as export_files:
            temp_dir = export_files.enter_context(temporary_export_dir())
            self._progress = progress = self.ui.createProgressDialog()
            progress.isBackgroundTranslucencyEnabled = True
            progress.cancelButtonText = ""
            progress.show("Fusion → GitHub", "Exporting the design…", 0, 2, 0)
            valid_formats, warnings = determine_valid_export_formats(design, formats)
            export_warnings.extend(warnings)
            if not valid_formats:
                progress.hide()
                return self._fail("None of the chosen file types can be exported from this design.")
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
                    self.message(NOTHING_PUSHED)
                    return False
                history_notes.append(linked_components_note(export.linked_components))

            # Questions (publication notice, identity) come with the progress
            # dialog hidden, so they can't end up behind it.
            request = PushRequest(
                profile_name=repo_name, design_name=design_name, design_id=design_id,
                commit_message=commit_msg, branch_override=override,
                history_notes=history_notes, fusion_version=fusion_version,
            )
            try:
                plan = self.controller.plan(request, exported, confirm=self.git_ui.confirm, ask_identity=self.ask_identity)
            except PushCancelled:
                self.message(NOTHING_PUSHED)
                return False
            except PushRefused as exc:
                return self._fail(error_catalog.explain(str(exc), nothing_changed=True))
            except (SettingsError, ValueError, OSError, CredentialError, GitError) as exc:
                return self._fail(error_catalog.explain(f"The backup didn't start:\n{redact_secrets(str(exc))}",
                                                        nothing_changed=True))

            # Asked here, on the main thread, so the background push doesn't.
            size_error, size_question = export_size_check(plan.exports)
            if size_error:
                return self._fail(size_error)
            if size_question:
                if not self.ask_yes_no(size_question):
                    self.message(NOTHING_PUSHED)
                    return False
                plan.large_files_confirmed = True

            remote_url = self.store.get(repo_name).get("url") or self.controller.origin_url(repo_path)
            return self._start_background_push(plan, repo_name, export_warnings, export_files, remote_url)

    def _start_background_push(self, plan, repo_name, export_warnings, export_files, remote_url="") -> bool:
        """Hand the plan to the worker; True (the dialog closes) once it is running."""
        bridge = self.ctx.bridge
        if bridge is None:
            return self._fail("The add-in's background push isn't available. Restart the add-in and try again.")
        controller = self.controller
        job = PushJob(
            repo_name=repo_name,
            exported_names=[rel for _, rel in plan.exports],
            warnings=list(export_warnings) + list(plan.notes),
            design_name=plan.design_name,
            remote_url=redact_secrets(remote_url or ""),
            fusion_version=plan.fusion_version,
            on_result=lambda result: controller.record_result(plan, result),
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
        except BaseException:
            cleanup.close()  # the exported files never reached a worker
            raise
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


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self, dialog: PushDialog):
        super().__init__()
        self.dialog = dialog

    def notify(self, args):
        try:
            self.dialog.validate(args)
        except Exception:
            # Leave OK enabled: execute() checks again and explains.
            if self.dialog.logger:
                self.dialog.logger.exception("ValidateInputsHandler failed")


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
    on_validate = ValidateInputsHandler(dialog)
    command.validateInputs.add(on_validate)
    on_execute = ExecuteHandler(dialog)
    command.execute.add(on_execute)
    ctx.handlers.extend([on_input_changed, on_validate, on_execute])
    dialog.show_load_messages()
    dialog.show_first_run_checks()
    return dialog


__all__ = [
    "ADD_NEW_OPTION",
    "COMMIT_PROMPT",
    "DialogContext",
    "FusionCommandGitUI",
    "OK_BUTTON_TEXT",
    "PushDialog",
    "check_git_available",
    "open_dialog",
]
