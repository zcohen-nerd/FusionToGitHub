"""This Add-In integrates Autodesk Fusion 360 with GitHub, allowing users to export
designs and push them to specified GitHub repositories, including changelog updates
and structured file logging. Features multi-select export format configuration."""

import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json
from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime
from urllib.parse import urlparse
import subprocess
import logging
import logging.handlers

# --- (Constants, Globals, Logger Setup - remain the same as previous version) ---

# ------------------------------------------------------------------------------
# GIT CONFIGURATION
# ------------------------------------------------------------------------------
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"

# ------------------------------------------------------------------------------
# SCRIPT-WIDE CONSTANTS & CONFIG
# ------------------------------------------------------------------------------
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")
ADD_NEW_OPTION = "+ Add new GitHub repo..."

LOG_DIR = os.path.expanduser("~/.PushToGitHub_AddIn_Data")
LOG_FILE_PATH = os.path.join(LOG_DIR, "PushToGitHub.log")

# ------------------------------------------------------------------------------
# GLOBALS FOR ADD-IN LIFECYCLE MANAGEMENT
# ------------------------------------------------------------------------------
app = None
ui = None
logger = None 

try:
    app = adsk.core.Application.get()
    ui = app.userInterface
except AttributeError:
    pass 

handlers = []
push_cmd_def = None
git_push_control = None

CMD_ID = "PushToGitHub_Cmd_ZAC_V6" # Updated ID for new version
CMD_NAME = "Push to GitHub (ZAC)"
CMD_TOOLTIP = "Exports/configures, updates changelog, and pushes design to GitHub."
PANEL_ID = "SolidUtilitiesAddinsPanel"
FALLBACK_PANEL_ID = "SolidScriptsAddinsPanel"
CONTROL_ID = CMD_ID + "_Control"

# ------------------------------------------------------------------------------
# LOGGER SETUP FUNCTION (same as before)
# ------------------------------------------------------------------------------
def setup_logger():
    global logger
    if logger is not None and logger.handlers:
        return

    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except OSError as e:
            print(f"Error creating log directory {LOG_DIR}: {e}. Logging disabled.")
            logger = logging.getLogger(CMD_ID + "_disabled") # Create dummy logger
            logger.addHandler(logging.NullHandler())
            return

    logger = logging.getLogger(CMD_ID)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        try:
            fh = logging.handlers.RotatingFileHandler(LOG_FILE_PATH, maxBytes=1*1024*1024, backupCount=3, encoding='utf-8')
            fh.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            logger.info(f"'{CMD_NAME}' Logger initialized. Log file: {LOG_FILE_PATH}")
        except Exception as e:
            print(f"Failed to initialize file logger for {CMD_NAME}: {e}. Logging disabled.")
            logger = logging.getLogger(CMD_ID + "_disabled") # Create dummy logger
            logger.addHandler(logging.NullHandler())
            if app: app.log(f"Failed to initialize file logger for {CMD_NAME}: {e}.", adsk.core.LogLevels.ErrorLogLevel)

# ------------------------------------------------------------------------------
# EVENT HANDLER: CREATES THE COMMAND UI *** MODIFIED ***
# ------------------------------------------------------------------------------
class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        local_app_ref = app if app else adsk.core.Application.get()
        local_ui_ref = ui if ui else local_app_ref.userInterface
        
        try:
            config = load_config()
            repo_names = list(config.keys())
            dropdown_items = [ADD_NEW_OPTION]
            if repo_names:
                dropdown_items.extend(sorted(repo_names))

            args.command.isAutoExecute = False
            args.command.isAutoTerminate = True
            inputs = args.command.commandInputs

            # --- Visible Inputs ---
            # 1. Action/Repo Selector
            repoSelectorInput = inputs.addDropDownCommandInput(
                "repoSelector", "Action / Select Repo",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for name_val in dropdown_items:
                repoSelectorInput.listItems.add(name_val, name_val == ADD_NEW_OPTION, "")

            # 2. New Repo Name
            inputs.addStringValueInput("newRepoName", "New Repo Name (if adding)", "")

            # 3. Git URL
            inputs.addStringValueInput("gitUrl", "Git URL (if adding)", "https://github.com/user/repo.git")
            
            # 4. Export Formats (config) *** CHANGED TO CHECKBOX DROPDOWN ***
            available_formats = ["f3d", "step", "iges", "sat", "stl", "dwg", "dxf"]
            default_formats_list = ["f3d", "step", "stl"] # Default selection for new repos or initial view
            exportFormatsDropdown = inputs.addDropDownCommandInput(
                "exportFormatsConfig", # Keep ID the same
                "Export Formats (config)", # Label
                adsk.core.DropDownStyles.CheckBoxListDropDownStyle # Style change!
            )
            # Add items (formats) to the checklist dropdown
            for fmt in available_formats:
                is_selected_by_default = fmt in default_formats_list
                # Add item: name (used internally), display name (shown to user), resourceFolder (optional icons)
                exportFormatsDropdown.listItems.add(fmt, is_selected_by_default, "")

            # 5. Default Commit Message Template
            inputs.addStringValueInput("defaultMessageConfig", "Default Commit Template (config)", "Design update: {filename}")

            # 6. Branch Format Template
            inputs.addStringValueInput("branchFormatConfig", "Branch Format (config)", "fusion-export/{filename}-{timestamp}")

            # 7. Commit Message (for push)
            inputs.addStringValueInput("commitMsgPush", "Commit Message (for this push)", "Updated design")


            # --- Execute Handler *** MODIFIED *** ---
            class ExecuteHandler(adsk.core.CommandEventHandler):
                def notify(self, execute_args: adsk.core.CommandEventArgs):
                    global logger # Ensure logger is accessible
                    current_app_ref = app if app else adsk.core.Application.get()
                    current_ui_ref = ui if ui else current_app_ref.userInterface
                    try:
                        cmd_inputs = execute_args.command.commandInputs
                        
                        selected_action_item = cmd_inputs.itemById("repoSelector").selectedItem
                        if not selected_action_item:
                            current_ui_ref.messageBox("No action or repository selected.")
                            return
                        selected_action = selected_action_item.name
                        
                        current_config = load_config()

                        # --- Read values from config fields ---
                        # ** Read from CheckBoxList Dropdown for Export Formats **
                        export_formats_input = cmd_inputs.itemById("exportFormatsConfig")
                        selected_formats = []
                        for item in export_formats_input.listItems:
                            if item.isSelected:
                                selected_formats.append(item.name) # Use internal name ('f3d', 'step', etc.)
                        # Ensure at least f3d is selected if user deselects all
                        export_formats_val = selected_formats if selected_formats else ["f3d"] 
                        
                        # Read other config fields
                        default_message_tpl_val = cmd_inputs.itemById("defaultMessageConfig").value.strip() or "Design update: {filename}"
                        branch_format_tpl_val = cmd_inputs.itemById("branchFormatConfig").value.strip() or "fusion-export/{filename}-{timestamp}"

                        # --- Process Action ---
                        if selected_action == ADD_NEW_OPTION:
                            # ... (Add new repo logic is the same, uses the *_val variables read above)
                            repo_name_to_add = cmd_inputs.itemById("newRepoName").value.strip()
                            git_url = cmd_inputs.itemById("gitUrl").value.strip()

                            # Basic validations
                            if not repo_name_to_add:
                                current_ui_ref.messageBox("New repository name cannot be empty.", CMD_NAME); return
                            if not git_url or not git_url.endswith(".git"):
                                current_ui_ref.messageBox("Invalid GitHub URL for new repo.", CMD_NAME); return
                            if repo_name_to_add in current_config:
                                current_ui_ref.messageBox(f"Repo '{repo_name_to_add}' already exists.", CMD_NAME); return

                            local_path = os.path.join(REPO_BASE_DIR, repo_name_to_add)
                            # ... (Clone logic remains the same) ...
                            if os.path.exists(local_path):
                                confirm = current_ui_ref.messageBox(f"Local path '{local_path}' exists.\nUse existing or cancel?", CMD_NAME, adsk.core.MessageBoxButtonTypes.YesNoButtonType)
                                if confirm == adsk.core.DialogResults.DialogNo: return
                            else:
                                os.makedirs(REPO_BASE_DIR, exist_ok=True)
                                current_ui_ref.messageBox(f"Cloning '{git_url}' into '{local_path}'...", CMD_NAME)
                                process = subprocess.run(["git", "clone", git_url, local_path], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                                if process.returncode != 0:
                                    err_msg_clone = f"Failed to clone repo:\n{process.stderr}"
                                    current_ui_ref.messageBox(err_msg_clone, CMD_NAME)
                                    if logger: logger.error(err_msg_clone)
                                    return
                                current_ui_ref.messageBox(f"Repository cloned successfully.", CMD_NAME)

                            # Save config using values read from inputs
                            current_config[repo_name_to_add] = {
                                "url": git_url, "path": local_path,
                                "exportFormats": export_formats_val, # From checklist
                                "defaultMessage": default_message_tpl_val,
                                "branchFormat": branch_format_tpl_val
                            }
                            save_config(current_config)
                            current_ui_ref.messageBox(f"Repository '{repo_name_to_add}' added. Restart command to select it for push.", CMD_NAME)
                            if logger: logger.info(f"Repository '{repo_name_to_add}' added with URL {git_url}.")
                            return # Done after adding

                        else: # An existing repository was selected
                            selected_repo_name = selected_action
                            if selected_repo_name not in current_config:
                                msg_repo_not_found = f"Error: Selected repo '{selected_repo_name}' not found in config."
                                current_ui_ref.messageBox(msg_repo_not_found, CMD_NAME)
                                if logger: logger.error(msg_repo_not_found); return
                            
                            selected_repo_details = current_config[selected_repo_name]
                            
                            # Update settings based on current state of inputs
                            selected_repo_details["exportFormats"] = export_formats_val # From checklist
                            selected_repo_details["defaultMessage"] = default_message_tpl_val
                            selected_repo_details["branchFormat"] = branch_format_tpl_val
                            
                            current_config[selected_repo_name] = selected_repo_details
                            save_config(current_config) # Save potentially updated settings
                            if logger: logger.info(f"Settings for repo '{selected_repo_name}' updated from dialog fields.")

                            # --- Proceed with PUSH ---
                            if not check_git_available(current_ui_ref): return
                            design = get_fusion_design()
                            if not design:
                                current_ui_ref.messageBox("No active Fusion design.", CMD_NAME); return

                            raw_name = design.rootComponent.name
                            clean_name = re.sub(r'\s+v\d+$', '', raw_name)
                            base_name = clean_name.replace(" ", "_") 

                            git_repo_path = os.path.expanduser(selected_repo_details["path"])
                            if not os.path.isdir(os.path.join(git_repo_path, ".git")):
                                current_ui_ref.messageBox(f"Path '{git_repo_path}' for repo '{selected_repo_name}' not Git repo.", CMD_NAME); return

                            temp_dir = os.path.join(git_repo_path, "temp_fusion_export")
                            os.makedirs(temp_dir, exist_ok=True)

                            # Use the now-updated export formats
                            formats_for_this_push = selected_repo_details.get("exportFormats", ["f3d"])
                            exported_files_paths = export_fusion_design(design, temp_dir, base_name, formats_for_this_push, current_ui_ref)

                            if not exported_files_paths:
                                current_ui_ref.messageBox("No files exported. Aborting.", CMD_NAME)
                                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                                return

                            commit_msg_for_this_push = cmd_inputs.itemById("commitMsgPush").value.strip()
                            filename_placeholder = base_name 
                            if not commit_msg_for_this_push: 
                                commit_msg_for_this_push = selected_repo_details["defaultMessage"].replace("{filename}", filename_placeholder)
                            else: 
                                commit_msg_for_this_push = commit_msg_for_this_push.replace("{filename}", filename_placeholder)
                            
                            final_file_paths_in_repo_relative = []
                            for file_path in exported_files_paths:
                                dest_path = os.path.join(git_repo_path, os.path.basename(file_path))
                                shutil.copy2(file_path, dest_path)
                                final_file_paths_in_repo_relative.append(os.path.basename(file_path))

                            branch_format_for_this_push = selected_repo_details.get("branchFormat", "fusion-export/{filename}-{timestamp}")
                            
                            branch_name_pushed = handle_git_operations(
                                git_repo_path,
                                final_file_paths_in_repo_relative,
                                commit_msg_for_this_push,
                                branch_format_for_this_push,
                                current_ui_ref,
                                base_name 
                            )

                            if branch_name_pushed:
                                current_ui_ref.messageBox(f"✅ Push successful to branch: {branch_name_pushed}\n(Settings for '{selected_repo_name}' also updated).", CMD_NAME)
                            else:
                                current_ui_ref.messageBox("Git operations completed with issues or were aborted.", CMD_NAME)
                            
                            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

                    except Exception as e:
                        error_message = 'ExecuteHandler failed: {}'.format(traceback.format_exc())
                        if current_ui_ref: current_ui_ref.messageBox(error_message, CMD_NAME)
                        if logger: logger.exception("ExecuteHandler failed") 
            
            on_execute = ExecuteHandler()
            args.command.execute.add(on_execute)
            handlers.append(on_execute)

        except Exception as e:
            error_message = 'GitCommandCreatedEventHandler failed: {}'.format(traceback.format_exc())
            final_ui_ref = local_ui_ref if local_ui_ref else ui
            if final_ui_ref: final_ui_ref.messageBox(error_message, CMD_NAME)
            if logger: logger.exception("GitCommandCreatedEventHandler failed")


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS (check_git_available, load_config, save_config, 
#                  get_fusion_design, export_fusion_design, handle_git_operations)
# - These remain the same as the previous version with logging fixes.
# - prompt_repo_settings function is no longer needed here.
# ------------------------------------------------------------------------------
def check_git_available(target_ui_ref):
    global logger
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, creationflags=flags)
        return True
    except FileNotFoundError:
        msg = f"Git executable not found. Check PATH or GIT_PYTHON_GIT_EXECUTABLE in script."
        target_ui_ref.messageBox(msg, "Git Not Found")
        if logger: logger.error(msg)
        return False
    except Exception as e:
        msg = f"Git version check failed: {str(e)}"
        target_ui_ref.messageBox(msg, "Git Error")
        if logger: logger.error(msg, exc_info=True)
        return False

def load_config():
    global logger, ui 
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f: json.dump({}, f)
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f: return json.load(f)
    except json.JSONDecodeError:
        final_ui_ref = ui 
        if not final_ui_ref and app: final_ui_ref = app.userInterface

        backup_path = CONFIG_PATH + ".bak_corrupted_" + datetime.now().strftime("%Y%m%d%H%M%S")
        if os.path.exists(CONFIG_PATH): shutil.copyfile(CONFIG_PATH, backup_path)
        msg = f"Config file corrupt. Backup made. New config created."
        if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
        if logger: logger.error(msg)
        with open(CONFIG_PATH, 'w') as f: json.dump({}, f)
        return {}
    except Exception as e:
         # Handle other potential file reading errors
         msg = f"Error loading config file '{CONFIG_PATH}': {str(e)}"
         final_ui_ref = ui
         if not final_ui_ref and app: final_ui_ref = app.userInterface
         if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
         if logger: logger.error(msg, exc_info=True)
         return {} # Return empty config on error


def save_config(config_data):
    global logger, ui
    try:
        with open(CONFIG_PATH, 'w') as f: json.dump(config_data, f, indent=4)
        if logger: logger.info(f"Configuration saved to {CONFIG_PATH}")
    except Exception as e:
        msg = f"Failed to save configuration: {str(e)}"
        final_ui_ref = ui
        if not final_ui_ref and app: final_ui_ref = app.userInterface
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

def export_fusion_design(design: adsk.fusion.Design, export_dir: str, base_name: str, formats_to_export: list, target_ui_ref):
    # ... (This function remains the same as the last version with logging fixes) ...
    global logger
    export_mgr = design.exportManager
    exported_file_paths = []
    root_comp = design.rootComponent

    for fmt in formats_to_export:
        fmt_lower = fmt.lower()
        export_file_name = f"{base_name}.{fmt_lower}"
        full_export_path = os.path.join(export_dir, export_file_name)
        options = None; export_executed_successfully = False

        try:
            if fmt_lower == "f3d": options = export_mgr.createFusionArchiveExportOptions(full_export_path, root_comp)
            elif fmt_lower in ["step", "stp"]: options = export_mgr.createSTEPExportOptions(full_export_path, root_comp)
            elif fmt_lower in ["iges", "igs"]: options = export_mgr.createIGESExportOptions(full_export_path, root_comp)
            elif fmt_lower == "sat": options = export_mgr.createSATExportOptions(full_export_path, root_comp)
            elif fmt_lower == "stl":
                options = export_mgr.createSTLExportOptions(root_comp, full_export_path)
                options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
            elif fmt_lower == "dwg" and hasattr(export_mgr, 'createDWGExportOptions'):
                 options = export_mgr.createDWGExportOptions(full_export_path, root_comp)
            elif fmt_lower == "dxf" and hasattr(export_mgr, 'createDXFExportOptions'):
                 options = export_mgr.createDXFExportOptions(full_export_path) 
            else:
                msg = f"Unsupported or unavailable export format: {fmt}. Skipping."
                target_ui_ref.messageBox(msg, CMD_NAME)
                if logger: logger.warning(msg)
                continue

            if options: export_executed_successfully = export_mgr.execute(options)
            
            if export_executed_successfully:
                if os.path.exists(full_export_path) and os.path.getsize(full_export_path) > 0:
                    exported_file_paths.append(full_export_path)
                    if logger: logger.info(f"Exported: {full_export_path}")
                elif os.path.exists(full_export_path): 
                     msg = f"Export reported success for {fmt_lower} but file is empty: {full_export_path}"
                     target_ui_ref.messageBox(msg, CMD_NAME)
                     if logger: logger.warning(msg)
                else: 
                    msg = f"Export reported success for {fmt_lower} but file not found: {full_export_path}"
                    target_ui_ref.messageBox(msg, CMD_NAME)
                    if logger: logger.warning(msg)
            elif options: 
                msg = f"Export execution failed or did not confirm success for {fmt_lower}: {full_export_path}"
                target_ui_ref.messageBox(msg, CMD_NAME)
                if logger: logger.warning(msg)

        except Exception as e:
            msg = f"Error exporting {fmt_lower} for '{base_name}'" 
            target_ui_ref.messageBox(msg + f":\n{str(e)}", CMD_NAME) 
            if logger: logger.exception(msg) 
            continue
            
    return exported_file_paths


def handle_git_operations(repo_path, file_basenames_to_add, commit_msg, branch_format_str, target_ui_ref, design_basename_for_branch):
    # ... (This function remains the same as the last version with changelog logic) ...
    global logger 
    repo = None 
    original_branch_name_for_cleanup = None
    stashed_changes_for_cleanup = False
    try:
        repo = Repo(repo_path)
        origin = repo.remotes.origin
        
        if repo.head.is_detached:
            try:
                default_branch_name = "main" 
                if default_branch_name not in repo.branches:
                    if "master" in repo.branches: default_branch_name = "master"
                    else: 
                         default_branch_remote_ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD', short=True)
                         default_branch_name = default_branch_remote_ref.split('/')[-1]

                repo.git.checkout(default_branch_name)
                original_branch_name_for_cleanup = default_branch_name
                msg = f"Repo was detached. Switched to '{default_branch_name}'."
                target_ui_ref.messageBox(msg, CMD_NAME)
                if logger: logger.info(msg)
            except Exception as e_det:
                msg = f"Repo is in detached HEAD and could not switch to default branch: {str(e_det)}. Please resolve manually."
                target_ui_ref.messageBox(msg, CMD_NAME)
                if logger: logger.error(msg, exc_info=True)
                return None
        else:
            original_branch_name_for_cleanup = repo.active_branch.name
        
        if logger: logger.info(f"Current branch for operations: {original_branch_name_for_cleanup}")

        if repo.is_dirty(untracked_files=False):
            repo.git.stash('push', '-u', '-m', 'fusion_git_addin_autostash')
            stashed_changes_for_cleanup = True
            if logger: logger.info("Stashed local changes.")

        if logger: logger.info(f"Pulling from origin/{original_branch_name_for_cleanup} with rebase...")
        origin.pull(original_branch_name_for_cleanup, rebase=True) 
        if logger: logger.info("Pull successful.")

        timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_branch_name = branch_format_str.replace("{timestamp}", timestamp_str).replace("{filename}", design_basename_for_branch)
        new_branch_name = re.sub(r'[^\w\-\./_]+', '_', new_branch_name) 

        if logger: logger.info(f"Creating and checking out new branch: {new_branch_name}")
        new_branch_head = repo.create_head(new_branch_name)
        new_branch_head.checkout()

        changelog_file_path = os.path.join(repo_path, "CHANGELOG.md")
        log_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        
        entry_lines = []
        entry_lines.append(f"## {log_timestamp} - {design_basename_for_branch}")
        entry_lines.append(f"- **Branch:** `{new_branch_name}`")
        entry_lines.append(f"- **Commit Message:** \"{commit_msg}\"")
        if file_basenames_to_add:
            entry_lines.append("- **Files Updated:**")
            for fname in file_basenames_to_add:
                entry_lines.append(f"  - `{fname}`")
        entry_lines.append("\n---\n") 
        new_entry_text = "\n".join(entry_lines) + "\n"
        existing_content = ""
        changelog_header = "# Changelog\n\n"
        files_to_commit_gitpython = list(file_basenames_to_add) 

        try:
            if os.path.exists(changelog_file_path):
                with open(changelog_file_path, "r", encoding="utf-8") as f_read:
                    existing_content = f_read.read()
                if existing_content.startswith(changelog_header):
                    existing_content = existing_content[len(changelog_header):] 
            with open(changelog_file_path, "w", encoding="utf-8") as f_write:
                f_write.write(changelog_header) 
                f_write.write(new_entry_text)   
                f_write.write(existing_content) 
            if logger: logger.info(f"Updated {changelog_file_path}")
            if "CHANGELOG.md" not in files_to_commit_gitpython: 
                 files_to_commit_gitpython.insert(0, "CHANGELOG.md")
        except IOError as e_io:
            msg = f"Error writing to CHANGELOG.md: {str(e_io)}. Proceeding without changelog update."
            target_ui_ref.messageBox(msg, CMD_NAME)
            if logger: logger.error(msg, exc_info=True)
        
        if logger: logger.info(f"Adding files to Git: {', '.join(files_to_commit_gitpython)}")
        repo.index.add(files_to_commit_gitpython) 
        
        if logger: logger.info(f"Committing with message: {commit_msg}")
        repo.index.commit(commit_msg)

        if logger: logger.info(f"Pushing branch {new_branch_name} to origin...")
        push_info_list = origin.push(new_branch_name, set_upstream=True)
        for push_info in push_info_list:
            if push_info.flags & (push_info.ERROR | push_info.REJECTED):
                err_msg = f"Git push failed for branch '{new_branch_name}': {push_info.summary}"
                target_ui_ref.messageBox(err_msg, CMD_NAME)
                if logger: logger.error(err_msg)
                raise GitCommandError(f"Push failed: {push_info.summary}") 
        if logger: logger.info("Push successful.")
        
        return new_branch_name

    except GitCommandError as e_git:
        msg = f"Git operation failed: {str(e_git)}"
        target_ui_ref.messageBox(msg, CMD_NAME)
        if logger: logger.error(msg, exc_info=True) 
        return None
    except Exception as e:
        msg = f"Unexpected error during Git operations"
        target_ui_ref.messageBox(msg + f":\n{str(e)}", CMD_NAME)
        if logger: logger.exception(msg)
        return None
    finally:
        try:
            if repo and original_branch_name_for_cleanup and repo.active_branch.name != original_branch_name_for_cleanup:
                if logger: logger.info(f"Attempting to switch back to original branch: {original_branch_name_for_cleanup}")
                repo.git.checkout(original_branch_name_for_cleanup)
            if repo and stashed_changes_for_cleanup:
                if logger: logger.info("Attempting to pop stashed changes on original branch...")
                repo.git.stash('pop')
                if logger: logger.info("Stash pop successful on original branch.")
        except GitCommandError as e_cleanup_git:
            cleanup_msg = f"Error during Git cleanup (checkout/stash pop on '{original_branch_name_for_cleanup}'): {str(e_cleanup_git)}"
            if target_ui_ref: target_ui_ref.messageBox(cleanup_msg + "\nPlease check repository state manually.", CMD_NAME)
            if logger: logger.warning(cleanup_msg, exc_info=True)
        except Exception as e_cleanup_general:
            cleanup_msg_gen = f"Unexpected error during Git cleanup"
            if logger: logger.warning(cleanup_msg_gen, exc_info=True)

# ------------------------------------------------------------------------------
# ADD-IN LIFECYCLE FUNCTIONS: run() and stop()
# ------------------------------------------------------------------------------
def run(context):
    # ... (run function remains the same as the last version with logging setup) ...
    global push_cmd_def, git_push_control, handlers, app, ui, logger
    
    if not app or not ui:
        try:
            temp_app_run = adsk.core.Application.get()
            if temp_app_run:
                globals()['app'] = temp_app_run 
                globals()['ui'] = temp_app_run.userInterface
            if not globals()['ui']: 
                print("CRITICAL: Could not obtain UserInterface object in run(). Add-in cannot start.")
                return
        except Exception as e_init_run:
            print(f"CRITICAL: Exception while re-getting app/ui in run(): {traceback.format_exc()}")
            return
    
    try:
        setup_logger() # Setup file logger
    except Exception as e_log_setup:
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
        if logger and target_panel: logger.info(f"Primary panel '{PANEL_ID}' found: {target_panel.name if target_panel else 'No'}")

        if not target_panel:
            if logger: logger.info(f"Primary panel '{PANEL_ID}' not found. Trying fallbacks.")
            design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if design_workspace:
                possible_fallback_ids = [FALLBACK_PANEL_ID, "ToolsSolidPythonScriptsPanel", "FusionSolidScriptPanel"]
                for panel_id_option in possible_fallback_ids:
                    tb_panel_candidate = design_workspace.toolbarPanels.itemById(panel_id_option)
                    if tb_panel_candidate:
                        target_panel = tb_panel_candidate
                        if logger: logger.info(f"Found fallback panel: '{target_panel.id}' ({target_panel.name})")
                        break
            if not target_panel and logger: logger.warning(f"No suitable fallback panel found in Design workspace.")
        
        if target_panel:
            if logger: logger.info(f"Target panel '{target_panel.id if target_panel else 'None'}' being used. Attempting to add/find control '{CONTROL_ID}'.")
            
            git_push_control = target_panel.controls.itemById(CONTROL_ID) 
            if git_push_control and git_push_control.isValid: 
                if logger: logger.info(f"Command control '{CONTROL_ID}' already exists in panel '{target_panel.id}'. Re-using.")
            else: 
                git_push_control = target_panel.controls.addCommand(push_cmd_def, CONTROL_ID) 
                if logger: logger.info(f"New command control '{CONTROL_ID}' {'created successfully' if git_push_control and git_push_control.isValid else 'FAILED to create'}.")
            
            if git_push_control and git_push_control.isValid:
                git_push_control.isPromotedByDefault = True 
                git_push_control.isPromoted = True        
                git_push_control.isVisible = True         
                if logger: logger.info(f"Command control '{CONTROL_ID}' configured for visibility in panel '{target_panel.id}'.")
            else:
                if logger: logger.error(f"Command control '{CONTROL_ID}' is None or invalid in panel '{target_panel.id}'. Button not visible.")
        else:
            msg = f"Could not find any target panel ('{PANEL_ID}' or fallbacks) to add the '{CMD_NAME}' button."
            if ui: ui.messageBox(msg, "Add-In UI Error")
            if logger: logger.error(msg)

        adsk.autoTerminate(False)
        if logger: logger.info(f"'{CMD_NAME}' Add-In Loaded and running.")

    except:
        error_msg = 'Failed to run the Add-In (run function)'
        if logger: logger.exception(error_msg) 
        else: 
            final_error_msg_run = f"{error_msg}:\n{traceback.format_exc()}"
            if ui: ui.messageBox(final_error_msg_run, CMD_NAME + " - Critical Error")
            elif app: app.log(final_error_msg_run, adsk.core.LogLevels.CriticalLogLevel)
            else: print(final_error_msg_run)
        adsk.autoTerminate(True)

def stop(context):
    # ... (stop function remains the same as the last version with logger shutdown) ...
    global push_cmd_def, git_push_control, handlers, app, ui, logger
    
    current_app_ref = app 
    current_ui_ref = ui
    if not current_app_ref or not current_ui_ref:
        try:
            temp_app_stop = adsk.core.Application.get()
            if temp_app_stop:
                if not current_app_ref: globals()['app'] = temp_app_stop; current_app_ref = temp_app_stop
                if not current_ui_ref: globals()['ui'] = temp_app_stop.userInterface; current_ui_ref = temp_app_stop.userInterface
            if not current_ui_ref:
                print("CRITICAL: Could not obtain UserInterface in stop(). Cannot stop cleanly.")
                if current_app_ref and logger : logger.critical("Could not obtain UserInterface in stop().")
                elif current_app_ref: current_app_ref.log("CRITICAL: Could not obtain UserInterface in stop().", adsk.core.LogLevels.CriticalLogLevel)
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in stop(): {traceback.format_exc()}")
            return
            
    log_stop_msg = f"'{CMD_NAME}' stop() called."
    if logger: logger.info(log_stop_msg)
    else: print(log_stop_msg) # Print if logger isn't available

    try:
        if git_push_control and git_push_control.isValid:
            git_push_control.deleteMe()
        
        if push_cmd_def and push_cmd_def.isValid:
            push_cmd_def.deleteMe()

        handlers.clear() 

        if logger: 
            logger.info(f"'{CMD_NAME}' Add-In Stopped. Shutting down logger.")
            # Shutdown logging
            for handler in logger.handlers[:]: # Iterate over a copy
                handler.close()
                logger.removeHandler(handler)
            # logging.shutdown() # This shuts down ALL logging, might affect other add-ins. Avoid it.
            logger = None # Reset global logger variable


    except:
        error_msg = 'Failed to stop the Add-In cleanly (stop function)'
        if logger: logger.exception(error_msg)
        else:
            final_error_msg_stop = f"{error_msg}:\n{traceback.format_exc()}"
            if current_ui_ref: current_ui_ref.messageBox(final_error_msg_stop, CMD_NAME + " - Stop Error")
            elif current_app_ref: current_app_ref.log(final_error_msg_stop, adsk.core.LogLevels.ErrorLogLevel)
            else: print(final_error_msg_stop)
