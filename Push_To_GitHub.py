"""Push to GitHub (ZAC) — V7.4
Export → changelog → branch → commit → push.
Key fix: pass ABSOLUTE exported paths into git ops, then relpath them for `git add`.
Also includes: progress dialog fix, double-init guard, toolbar de-dupe, robust path checks.
"""

import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json, subprocess, logging, logging.handlers
from datetime import datetime

VERSION = "V7.4"

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

LOG_DIR = os.path.expanduser("~/.PushToGitHub_AddIn_Data")
LOG_FILE_PATH = os.path.join(LOG_DIR, "PushToGitHub.log")

CMD_ID = "PushToGitHub_Cmd_ZAC_V7_4"
CMD_NAME = "Push to GitHub (ZAC)"
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


def export_fusion_design(design: adsk.fusion.Design, export_dir: str, base_name: str, formats_to_export: list, target_ui_ref):
    global logger
    em = design.exportManager
    root = design.rootComponent
    exported = []

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
                opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
            elif fmt == "dwg" and hasattr(em, "createDWGExportOptions"):
                target_ui_ref.messageBox("DWG export requires a drawing; skipping.", CMD_NAME)
                continue
            elif fmt == "dxf" and hasattr(em, "createDXFExportOptions"):
                target_ui_ref.messageBox("DXF export requires a sketch/drawing; skipping.", CMD_NAME)
                continue
            else:
                if logger: logger.warning("Unsupported/unavailable export format: %s", fmt)
                continue

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
            config = load_config()
            repo_names = sorted(list(config.keys()))
            dropdown_items = [ADD_NEW_OPTION] + repo_names if repo_names else [ADD_NEW_OPTION]

            args.command.isAutoExecute = False
            args.command.isAutoTerminate = True
            inputs = args.command.commandInputs

            # Repo selector
            repoSelectorInput = inputs.addDropDownCommandInput(
                "repoSelector", "Action / Select Repo",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for name_val in dropdown_items:
                repoSelectorInput.listItems.add(name_val, False, "")
            if repo_names:
                for li in repoSelectorInput.listItems:
                    if li.name == repo_names[0]:
                        li.isSelected = True
                        break
            else:
                repoSelectorInput.listItems.item(0).isSelected = True

            # New-repo inputs
            inputs.addStringValueInput("newRepoName", "New Repo Name (if adding)", "")
            inputs.addStringValueInput("gitUrl", "Git URL (if adding)", "https://github.com/user/repo.git")

            # Export formats (checkbox dropdown)
            available_formats = ["f3d", "step", "iges", "sat", "stl", "dwg", "dxf"]
            default_formats_list = ["f3d", "step", "stl"]
            exportFormatsDropdown = inputs.addDropDownCommandInput(
                "exportFormatsConfig", "Export Formats (config)",
                adsk.core.DropDownStyles.CheckBoxDropDownStyle
            )
            for fmt in available_formats:
                exportFormatsDropdown.listItems.add(fmt, fmt in default_formats_list, "")

            # Templates and per-push message
            inputs.addStringValueInput("defaultMessageConfig", "Default Commit Template (config)", "Design update: {filename}")
            inputs.addStringValueInput("branchFormatConfig", "Branch Format (config)", "fusion-export/{filename}-{timestamp}")
            inputs.addStringValueInput("commitMsgPush", "Commit Message (for this push)", "Updated design")

            # Apply saved settings for selected repo
            def apply_repo_settings(repo_name: str):
                cfg = load_config()
                det = cfg.get(repo_name, {})
                saved_formats = set(det.get("exportFormats", []))
                for item in exportFormatsDropdown.listItems:
                    item.isSelected = (item.name in saved_formats) if saved_formats else (item.name in default_formats_list)
                inputs.itemById("defaultMessageConfig").value = det.get("defaultMessage", "Design update: {filename}")
                inputs.itemById("branchFormatConfig").value = det.get("branchFormat", "fusion-export/{filename}-{timestamp}")

            sel_item = repoSelectorInput.selectedItem
            if sel_item and sel_item.name != ADD_NEW_OPTION:
                apply_repo_settings(sel_item.name)

            class InputChangedHandler(adsk.core.InputChangedEventHandler):
                def __init__(self, repoSelector):
                    super().__init__()
                    self._repoSelector = repoSelector
                def notify(self, ic_args: adsk.core.InputChangedEventArgs):
                    if ic_args.input and ic_args.input.id == "repoSelector":
                        sel = self._repoSelector.selectedItem
                        if sel and sel.name != ADD_NEW_OPTION:
                            apply_repo_settings(sel.name)

            on_input_changed = InputChangedHandler(repoSelectorInput)
            args.command.inputChanged.add(on_input_changed)
            handlers.append(on_input_changed)

            # Execute handler
            class ExecuteHandler(adsk.core.CommandEventHandler):
                def notify(self, execute_args: adsk.core.CommandEventArgs):
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
                        current_config = load_config()

                        # Formats
                        export_formats_input = cmd_inputs.itemById("exportFormatsConfig")
                        selected_formats = [item.name for item in export_formats_input.listItems if item.isSelected]
                        export_formats_val = selected_formats if selected_formats else ["f3d"]

                        # Templates
                        default_message_tpl_val = cmd_inputs.itemById("defaultMessageConfig").value.strip() or "Design update: {filename}"
                        branch_format_tpl_val = cmd_inputs.itemById("branchFormatConfig").value.strip() or "fusion-export/{filename}-{timestamp}"

                        # ADD NEW
                        if selected_action == ADD_NEW_OPTION:
                            repo_name_to_add = cmd_inputs.itemById("newRepoName").value.strip()
                            git_url = cmd_inputs.itemById("gitUrl").value.strip()
                            if not repo_name_to_add:
                                current_ui_ref.messageBox("New repository name cannot be empty.", CMD_NAME); return
                            if not git_url or not git_url.endswith(".git"):
                                current_ui_ref.messageBox("Invalid GitHub URL for new repo.", CMD_NAME); return
                            if repo_name_to_add in current_config:
                                current_ui_ref.messageBox(f"Repo '{repo_name_to_add}' already exists.", CMD_NAME); return

                            local_path = os.path.join(REPO_BASE_DIR, repo_name_to_add)
                            os.makedirs(REPO_BASE_DIR, exist_ok=True)

                            progress = current_ui_ref.createProgressDialog()
                            progress.isBackgroundTranslucencyEnabled = True
                            progress.cancelButtonText = ""
                            progress.show("Clone Repository", "Cloning repository…", 0, 1, 0)

                            if os.path.exists(local_path):
                                confirm = current_ui_ref.messageBox(
                                    f"Local path '{local_path}' exists.\nUse existing or cancel?", CMD_NAME,
                                    adsk.core.MessageBoxButtonTypes.YesNoButtonType)
                                if confirm == adsk.core.DialogResults.DialogNo:
                                    progress.hide()
                                    return
                            else:
                                try:
                                    _git(os.path.dirname(local_path), "clone", git_url, local_path)
                                except Exception as e:
                                    progress.hide()
                                    err_msg_clone = f"Failed to clone repo:\n{str(e)}"
                                    current_ui_ref.messageBox(err_msg_clone, CMD_NAME)
                                    if logger: logger.error(err_msg_clone)
                                    return

                            if progress: progress.hide()

                            current_config[repo_name_to_add] = {
                                "url": git_url,
                                "path": local_path.replace("/", os.sep),
                                "exportFormats": export_formats_val,
                                "defaultMessage": default_message_tpl_val,
                                "branchFormat": branch_format_tpl_val
                            }
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
                        selected_repo_details["exportFormats"] = export_formats_val
                        selected_repo_details["defaultMessage"] = default_message_tpl_val
                        selected_repo_details["branchFormat"] = branch_format_tpl_val
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

                        temp_dir = os.path.join(git_repo_path, "temp_fusion_export")
                        os.makedirs(temp_dir, exist_ok=True)

                        progress = current_ui_ref.createProgressDialog()
                        progress.isBackgroundTranslucencyEnabled = True
                        progress.cancelButtonText = ""
                        progress.show("Fusion → GitHub", "Exporting design…", 0, 2, 0)

                        formats_for_this_push = selected_repo_details.get("exportFormats", ["f3d"])
                        exported_files_paths = export_fusion_design(design, temp_dir, base_name, formats_for_this_push, current_ui_ref)
                        if not exported_files_paths:
                            if progress: progress.hide()
                            current_ui_ref.messageBox("No files exported. Aborting.", CMD_NAME)
                            return

                        # Copy to repo root; collect ABS DEST PATHS
                        final_abs = []
                        for src in exported_files_paths:
                            fname = os.path.basename(src)
                            dst = os.path.join(git_repo_path, fname)
                            try:
                                shutil.copy2(src, dst)
                            except Exception as e:
                                if progress: progress.hide()
                                current_ui_ref.messageBox(f"Copy failed:\nSRC: {src}\nDST: {dst}\n{e}", CMD_NAME)
                                if logger: logger.error("Copy failed %s -> %s : %s", src, dst, e, exc_info=True)
                                return
                            if not os.path.exists(dst) or os.path.getsize(dst) == 0:
                                if progress: progress.hide()
                                current_ui_ref.messageBox(f"Copied file missing/empty:\n{dst}", CMD_NAME)
                                if logger: logger.error("Copied file missing/empty: %s", dst)
                                return
                            final_abs.append(os.path.normpath(dst))
                            if logger: logger.info("Copied -> %s (%d bytes)", dst, os.path.getsize(dst))

                        if progress:
                            progress.message = "Pushing to GitHub…"
                            progress.progressValue = 1

                        commit_msg_for_this_push = cmd_inputs.itemById("commitMsgPush").value.strip() or selected_repo_details["defaultMessage"]
                        branch_format_for_this_push = selected_repo_details.get("branchFormat", "fusion-export/{filename}-{timestamp}")

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
                            current_ui_ref.messageBox(
                                f"✅ Push successful to branch: {branch_name_pushed}\n(Settings for '{selected_repo_name}' updated).",
                                CMD_NAME
                            )
                        else:
                            current_ui_ref.messageBox("Git operations completed with issues or were aborted.", CMD_NAME)

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

