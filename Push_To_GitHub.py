"""Push to GitHub (ZAC) — V7.7
Export → changelog → branch → commit → push.
V7.7 formalizes dependency packaging and adds an offline CLI harness.
"""

import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json, subprocess, logging, logging.handlers, tempfile
from contextlib import contextmanager
from datetime import datetime

VERSION = "V7.7"

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
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run([GIT_EXE, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, creationflags=flags)
        return True
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
handlers = []
push_cmd_def = None
git_push_control = None
is_initialized = False  # guard against double run()

try:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    print(f"[PushToGitHub] Loaded {VERSION} with CMD_ID={CMD_ID}")
except AttributeError:
    pass

# -----------------------------
# Logger
# -----------------------------
def setup_logger():
    global logger
    if logger is not None and logger.handlers:
        return

    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except OSError as e:
            print(f"Error creating log directory {LOG_DIR}: {e}. Logging disabled.")
            logger = logging.getLogger(CMD_ID + "_disabled")
            logger.addHandler(logging.NullHandler())
            return

    logger = logging.getLogger(CMD_ID)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        try:
            fh = logging.handlers.RotatingFileHandler(
                LOG_FILE_PATH, maxBytes=1 * 1024 * 1024, backupCount=3, encoding='utf-8'
            )
            fh.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            logger.info(f"'{CMD_NAME}' Logger initialized. Log file: {LOG_FILE_PATH}")
        except Exception as e:
            print(f"Failed to initialize file logger for {CMD_NAME}: {e}. Logging disabled.")
            logger = logging.getLogger(CMD_ID + "_disabled")
            logger.addHandler(logging.NullHandler())
            if app:
                app.log(f"Failed to initialize file logger for {CMD_NAME}: {e}.", adsk.core.LogLevels.ErrorLogLevel)

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
# Git ops (CLI), ABS paths in
# -----------------------------
def handle_git_operations(repo_path, file_abs_paths_to_add, commit_msg_template, branch_format_str, target_ui_ref, design_basename_for_branch):
    global logger
    our_stash_msg = 'fusion_git_addin_autostash'
    original_branch = None
    stashed = False
    try:
        # Validate origin
        remotes = _git_out(repo_path, "remote").splitlines()
        if "origin" not in remotes:
            target_ui_ref.messageBox("No 'origin' remote found in this repo.", CMD_NAME)
            if logger: logger.error("No 'origin' remote in %s", repo_path)
            return None

        # Determine current branch / detached
        head = _git_out(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        detached = (head.strip() == "HEAD")
        if not detached:
            original_branch = head.strip()

        if detached:
            try:
                ref = _git_out(repo_path, "symbolic-ref", "refs/remotes/origin/HEAD", "--short")  # e.g., origin/main
                default_branch = ref.split("/")[-1]
            except Exception:
                branches = set([b.strip().lstrip("* ").strip() for b in _git_out(repo_path, "branch").splitlines()])
                default_branch = "main" if "main" in branches else ("master" if "master" in branches else None)
            if not default_branch:
                target_ui_ref.messageBox("Unable to determine default branch while in detached HEAD.", CMD_NAME)
                if logger: logger.error("Cannot determine default branch")
                return None
            _git(repo_path, "checkout", default_branch)
            original_branch = default_branch
            if logger: logger.info("Detached HEAD → switched to '%s'", default_branch)

        # Stash local changes if dirty
        status = _git_out(repo_path, "status", "--porcelain")
        if status.strip():
            _git(repo_path, "stash", "push", "-u", "-m", our_stash_msg)
            stashed = True
            if logger: logger.info("Stashed local changes.")

        # Rebase pull
        _git(repo_path, "pull", "--rebase", "origin", original_branch)

        # New branch name
        timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_branch_name = branch_format_str.replace("{timestamp}", timestamp_str).replace("{filename}", design_basename_for_branch)
        new_branch_name = re.sub(r'[^\w\-\./_]+', '_', new_branch_name)

        # Create/checkout branch
        _git(repo_path, "checkout", "-b", new_branch_name)

        # Changelog
        changelog_file_path = os.path.join(repo_path, "CHANGELOG.md")
        log_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = (commit_msg_template or "Design update: {filename}")
        commit_msg = (commit_msg
                      .replace("{filename}", design_basename_for_branch)
                      .replace("{branch}", new_branch_name)
                      .replace("{timestamp}", timestamp_str))

        entry_lines = [
            f"## {log_timestamp} - {design_basename_for_branch}",
            f"- **Branch:** `{new_branch_name}`",
            f"- **Commit Message:** \"{commit_msg}\"",
        ]
        if file_abs_paths_to_add:
            entry_lines.append("- **Files Updated:**")
            entry_lines.extend([f"  - `{os.path.basename(f)}`" for f in file_abs_paths_to_add])
        entry_lines.append("\n---\n")

        changelog_header = "# Changelog\n\n"
        existing = ""
        if os.path.exists(changelog_file_path):
            with open(changelog_file_path, "r", encoding="utf-8") as fr:
                existing = fr.read()
            if existing.startswith(changelog_header):
                existing = existing[len(changelog_header):]
        with open(changelog_file_path, "w", encoding="utf-8") as fw:
            fw.write(changelog_header)
            fw.write("\n".join(entry_lines) + "\n")
            fw.write(existing)

        # Validate absolute existence
        files_abs = [os.path.join(repo_path, "CHANGELOG.md")] + [os.path.normpath(p) for p in (file_abs_paths_to_add or [])]
        missing = [p for p in files_abs if not os.path.exists(p)]
        if missing:
            # Log repo root listing to help diagnose
            try:
                listing = "\n".join(sorted(os.listdir(repo_path)))
            except Exception:
                listing = "(dir list failed)"
            msg = "Exported files not found in repo folder:\n" + "\n".join(missing) + f"\n\nRepo root listing:\n{listing}"
            target_ui_ref.messageBox(msg, CMD_NAME)
            if logger: logger.error(msg)
            return None

        # Convert to repo-relative for git add
        rels = ["CHANGELOG.md"]
        for p in (file_abs_paths_to_add or []):
            rels.append(os.path.relpath(os.path.normpath(p), repo_path))

        _git(repo_path, "add", *rels)
        _git(repo_path, "commit", "-m", commit_msg)
        _git(repo_path, "push", "-u", "origin", new_branch_name)

        return new_branch_name

    except Exception as e:
        msg = f"Git operation failed:\n{str(e)}"
        target_ui_ref.messageBox(msg, CMD_NAME)
        if logger: logger.error(msg, exc_info=True)
        return None
    finally:
        try:
            if original_branch:
                _git(repo_path, "checkout", original_branch, check=False)
            if stashed:
                stash_list = _git_out(repo_path, "stash", "list")
                if stash_list.splitlines() and our_stash_msg in stash_list.splitlines()[0]:
                    _git(repo_path, "stash", "pop", "stash@{0}", check=False)
                else:
                    if logger: logger.warning("Leaving changes stashed; top stash not ours.")
        except Exception:
            if logger: logger.warning("Cleanup failed", exc_info=True)

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
            format_settings_table = export_inputs.addTableCommandInput(
                "formatSettingsTable", "Format Settings", 2,
                adsk.core.TablePresentationStyles.minimalTablePresentationStyle
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
                update_validation()

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
                        if isinstance(meta_section, dict):
                            meta_section["lastSelectedRepo"] = selected_repo_name
                            meta_section["lastCommitMessage"] = commit_msg_for_this_push
                        current_config[selected_repo_name] = selected_repo_details
                        save_config(current_config)

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

                            # Copy to repo root; collect ABS DEST PATHS
                            for src in exported_files_paths:
                                fname = os.path.basename(src)
                                exported_display_names.append(fname)
                                dst = os.path.join(git_repo_path, fname)
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
                                if logger:
                                    logger.info(
                                        "Copied -> %s (%d bytes)",
                                        dst,
                                        os.path.getsize(dst),
                                    )

                        if progress:
                            progress.message = "Pushing to GitHub…"
                            progress.progressValue = 1

                        branch_name_pushed = handle_git_operations(
                            git_repo_path,
                            final_abs,  # ABS paths
                            commit_msg_for_this_push,
                            branch_format_for_this_push,
                            current_ui_ref,
                            base_name
                        )

                        if progress:
                            progress.progressValue = 2
                            progress.hide()

                        if branch_name_pushed:
                            summary_lines = [
                                f"✅ Push successful to branch: {branch_name_pushed}",
                                f"Settings for '{selected_repo_name}' updated.",
                            ]
                            if exported_display_names:
                                summary_lines.append("")
                                summary_lines.append("Exported files:")
                                summary_lines.extend(
                                    f" • {name}"
                                    for name in exported_display_names
                                )
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

