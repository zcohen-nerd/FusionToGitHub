"""This Add-In integrates Autodesk Fusion 360 with GitHub, allowing users to export
designs and push them to specified GitHub repositories."""

import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json
from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime
from urllib.parse import urlparse
import subprocess

# ------------------------------------------------------------------------------
# GIT CONFIGURATION
# ------------------------------------------------------------------------------
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"

# ------------------------------------------------------------------------------
# SCRIPT-WIDE CONSTANTS
# ------------------------------------------------------------------------------
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")
ADD_NEW_OPTION = "+ Add new GitHub repo..."
# EDIT_EXISTING_OPTION is no longer used in repoSelector

# ------------------------------------------------------------------------------
# GLOBALS FOR ADD-IN LIFECYCLE MANAGEMENT
# ------------------------------------------------------------------------------
app = None
ui = None
try:
    app = adsk.core.Application.get()
    ui = app.userInterface
except AttributeError:
    pass

handlers = []
push_cmd_def = None
git_push_control = None

CMD_ID = "PushToGitHub_Cmd_ZAC_V3" # Updated ID
CMD_NAME = "Push to GitHub (ZAC)"
CMD_TOOLTIP = "Exports/configures and pushes design to a GitHub repository."
PANEL_ID = "SolidUtilitiesAddinsPanel"
FALLBACK_PANEL_ID = "SolidScriptsAddinsPanel"
CONTROL_ID = CMD_ID + "_Control"

# ------------------------------------------------------------------------------
# EVENT HANDLER: CREATES THE COMMAND UI
# ------------------------------------------------------------------------------
class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        local_app_ref = app if app else adsk.core.Application.get()
        local_ui_ref = ui if ui else local_app_ref.userInterface
        
        try:
            config = load_config()
            repo_names = list(config.keys())
            dropdown_items = [ADD_NEW_OPTION] # Start with Add New
            if repo_names:
                dropdown_items.extend(sorted(repo_names)) # Add existing repos, sorted

            args.command.isAutoExecute = False
            args.command.isAutoTerminate = True # Dialog closes after OK
            inputs = args.command.commandInputs

            # --- Visible Inputs ---
            # 1. Action/Repo Selector
            global repoSelectorInput # Make it accessible if needed by ExecuteHandler (though usually by ID)
            repoSelectorInput = inputs.addDropDownCommandInput(
                "repoSelector",
                "Action / Select Repo",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for name_val in dropdown_items:
                repoSelectorInput.listItems.add(name_val, name_val == ADD_NEW_OPTION, "")

            # 2. New Repo Name (only used if "Add new..." is selected)
            inputs.addStringValueInput("newRepoName", "New Repo Name (if adding)", "")

            # 3. Git URL (only used if "Add new..." is selected)
            inputs.addStringValueInput("gitUrl", "Git URL (if adding)", "https://github.com/user/repo.git")
            
            # 4. Export Formats (for config of new or existing selected repo)
            inputs.addStringValueInput("exportFormatsConfig", "Export Formats (config)", "f3d,step,stl")

            # 5. Default Commit Message Template (for config of new or existing selected repo)
            inputs.addStringValueInput("defaultMessageConfig", "Default Commit Template (config)", "Design update: {filename}")

            # 6. Branch Format Template (for config of new or existing selected repo)
            inputs.addStringValueInput("branchFormatConfig", "Branch Format (config)", "fusion-export/{filename}-{timestamp}")

            # 7. Commit Message (for the current push operation)
            inputs.addStringValueInput("commitMsgPush", "Commit Message (for this push)", "Updated design")


            # --- Execute Handler ---
            class ExecuteHandler(adsk.core.CommandEventHandler):
                def notify(self, execute_args: adsk.core.CommandEventArgs):
                    current_app_ref = app if app else adsk.core.Application.get()
                    current_ui_ref = ui if ui else current_app_ref.userInterface
                    try:
                        cmd_inputs = execute_args.command.commandInputs # Get inputs from execute_args
                        
                        selected_action_item = cmd_inputs.itemById("repoSelector").selectedItem
                        if not selected_action_item:
                            current_ui_ref.messageBox("No action or repository selected.")
                            return
                        selected_action = selected_action_item.name
                        
                        current_config = load_config()

                        # Get values from all config fields - they are always visible
                        # These will be used for "Add New" or to update an existing repo's config
                        export_formats_val = [f.strip().lower() for f in cmd_inputs.itemById("exportFormatsConfig").value.split(",") if f.strip()] or ["f3d"]
                        default_message_tpl_val = cmd_inputs.itemById("defaultMessageConfig").value.strip() or "Design update: {filename}"
                        branch_format_tpl_val = cmd_inputs.itemById("branchFormatConfig").value.strip() or "fusion-export/{filename}-{timestamp}"

                        if selected_action == ADD_NEW_OPTION:
                            repo_name_to_add = cmd_inputs.itemById("newRepoName").value.strip()
                            git_url = cmd_inputs.itemById("gitUrl").value.strip()

                            if not repo_name_to_add:
                                current_ui_ref.messageBox("New repository name cannot be empty.", CMD_NAME)
                                return
                            if not git_url or not git_url.endswith(".git"):
                                current_ui_ref.messageBox("Invalid GitHub URL for new repo. It must end in .git", CMD_NAME)
                                return
                            if repo_name_to_add in current_config:
                                current_ui_ref.messageBox(f"Repository '{repo_name_to_add}' already exists in configuration.", CMD_NAME)
                                return

                            local_path = os.path.join(REPO_BASE_DIR, repo_name_to_add)
                            if os.path.exists(local_path):
                                confirm = current_ui_ref.messageBox(f"Local path '{local_path}' already exists.\nUse existing or cancel?", CMD_NAME, adsk.core.MessageBoxButtonTypes.YesNoButtonType)
                                if confirm == adsk.core.DialogResults.DialogNo: return
                            else:
                                os.makedirs(REPO_BASE_DIR, exist_ok=True)
                                current_ui_ref.messageBox(f"Cloning '{git_url}' into '{local_path}'...", CMD_NAME)
                                process = subprocess.run(["git", "clone", git_url, local_path], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                                if process.returncode != 0:
                                    current_ui_ref.messageBox(f"Failed to clone repo:\n{process.stderr}", CMD_NAME)
                                    return
                                current_ui_ref.messageBox(f"Repository cloned successfully.", CMD_NAME)
                            
                            current_config[repo_name_to_add] = {
                                "url": git_url, "path": local_path,
                                "exportFormats": export_formats_val,
                                "defaultMessage": default_message_tpl_val,
                                "branchFormat": branch_format_tpl_val
                            }
                            save_config(current_config)
                            current_ui_ref.messageBox(f"Repository '{repo_name_to_add}' added. Restart command to select it for push.", CMD_NAME)
                            return # Done after adding

                        else: # An existing repository was selected (selected_action is the repo name)
                            selected_repo_name = selected_action
                            if selected_repo_name not in current_config:
                                current_ui_ref.messageBox(f"Error: Selected repository '{selected_repo_name}' not found in config.", CMD_NAME)
                                if app: app.log(f"Config error: Repo '{selected_repo_name}' not found.", adsk.core.LogLevels.ErrorLogLevel)
                                return
                            
                            selected_repo_details = current_config[selected_repo_name]

                            # Implicitly update the selected repo's settings from the visible fields
                            selected_repo_details["exportFormats"] = export_formats_val
                            selected_repo_details["defaultMessage"] = default_message_tpl_val
                            selected_repo_details["branchFormat"] = branch_format_tpl_val
                            # We don't update URL or path for an existing repo via these main fields
                            # newRepoName and gitUrl fields are ignored when an existing repo is selected.

                            current_config[selected_repo_name] = selected_repo_details
                            save_config(current_config)
                            if app: app.log(f"Settings for repository '{selected_repo_name}' updated from dialog fields.", adsk.core.LogLevels.InfoLogLevel)

                            # Now, proceed with the PUSH operation using the (potentially updated) selected_repo_details
                            if not check_git_available(current_ui_ref): return
                            design = get_fusion_design()
                            if not design:
                                current_ui_ref.messageBox("No active Fusion design to export.", CMD_NAME)
                                return

                            raw_name = design.rootComponent.name
                            clean_name = re.sub(r'\s+v\d+$', '', raw_name)
                            base_name = clean_name.replace(" ", "_") # For filenames and placeholders

                            git_repo_path = os.path.expanduser(selected_repo_details["path"])
                            if not os.path.isdir(os.path.join(git_repo_path, ".git")):
                                current_ui_ref.messageBox(f"Path '{git_repo_path}' for repo '{selected_repo_name}' is not a Git repository.", CMD_NAME)
                                return

                            temp_dir = os.path.join(git_repo_path, "temp_fusion_export")
                            os.makedirs(temp_dir, exist_ok=True)

                            # Use the (potentially updated) export formats from selected_repo_details
                            formats_for_this_push = selected_repo_details.get("exportFormats", ["f3d"])
                            exported_files_paths = export_fusion_design(design, temp_dir, base_name, formats_for_this_push, current_ui_ref)

                            if not exported_files_paths:
                                current_ui_ref.messageBox("No files exported. Aborting Git operations.", CMD_NAME)
                                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                                return

                            commit_msg_for_this_push = cmd_inputs.itemById("commitMsgPush").value.strip()
                            filename_placeholder = base_name 
                            if not commit_msg_for_this_push: # If user left commit message blank for this push
                                commit_msg_for_this_push = selected_repo_details["defaultMessage"].replace("{filename}", filename_placeholder)
                            else: # User provided a message, still replace placeholder if they used it
                                commit_msg_for_this_push = commit_msg_for_this_push.replace("{filename}", filename_placeholder)
                            
                            final_file_paths_in_repo_relative = []
                            for file_path in exported_files_paths:
                                dest_path = os.path.join(git_repo_path, os.path.basename(file_path))
                                shutil.copy2(file_path, dest_path)
                                final_file_paths_in_repo_relative.append(os.path.basename(file_path))

                            # Use the (potentially updated) branch format from selected_repo_details
                            branch_format_for_this_push = selected_repo_details.get("branchFormat", "fusion-export/{filename}-{timestamp}")
                            
                            branch_name_pushed = handle_git_operations(
                                git_repo_path,
                                final_file_paths_in_repo_relative,
                                commit_msg_for_this_push,
                                branch_format_for_this_push,
                                current_ui_ref,
                                base_name # For {filename} placeholder in branch name
                            )

                            if branch_name_pushed:
                                current_ui_ref.messageBox(f"✅ Successfully exported and pushed to branch: {branch_name_pushed}\nCreate a pull request on GitHub to merge.", CMD_NAME)
                            else:
                                current_ui_ref.messageBox("Git operations completed with issues or were aborted.", CMD_NAME)
                            
                            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

                    except Exception as e:
                        error_message = 'ExecuteHandler failed: {}'.format(traceback.format_exc())
                        if current_ui_ref: current_ui_ref.messageBox(error_message, CMD_NAME)
                        if app: app.log(error_message, adsk.core.LogLevels.ErrorLogLevel)
            
            on_execute = ExecuteHandler()
            args.command.execute.add(on_execute)
            handlers.append(on_execute)

        except Exception as e:
            error_message = 'GitCommandCreatedEventHandler failed: {}'.format(traceback.format_exc())
            final_ui_ref = local_ui_ref if local_ui_ref else ui
            if final_ui_ref: final_ui_ref.messageBox(error_message, CMD_NAME)
            if app: app.log(error_message, adsk.core.LogLevels.ErrorLogLevel)

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS (check_git_available, load_config, save_config, get_fusion_design, export_fusion_design, handle_git_operations)
# These functions remain largely the same as the previous version that had app.log fixes.
# The prompt_repo_settings function is no longer used by ExecuteHandler.
# Ensure handle_git_operations correctly uses its parameters.
# ------------------------------------------------------------------------------

def check_git_available(target_ui_ref):
    global app
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, creationflags=flags)
        return True
    except FileNotFoundError:
        msg = f"Git executable not found. Ensure Git is installed and in PATH, or GIT_PYTHON_GIT_EXECUTABLE ('{os.environ.get('GIT_PYTHON_GIT_EXECUTABLE')}') is set."
        target_ui_ref.messageBox(msg, "Git Not Found")
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
        return False
    except Exception as e:
        msg = f"Git version check failed: {str(e)}\nEnsure Git is installed correctly."
        target_ui_ref.messageBox(msg, "Git Error")
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
        return False

def load_config():
    global app, ui 
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f: json.dump({}, f)
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f: return json.load(f)
    except json.JSONDecodeError:
        final_ui_ref = ui 
        if not final_ui_ref and app: final_ui_ref = app.userInterface

        backup_path = CONFIG_PATH + ".bak_corrupted_" + datetime.now().strftime("%Y%m%d%H%M%S")
        if os.path.exists(CONFIG_PATH): shutil.copyfile(CONFIG_PATH, backup_path) # Check if exists before copy
        msg = f"Configuration file was corrupted. Backup made to '{backup_path}'. New config file created."
        if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
        with open(CONFIG_PATH, 'w') as f: json.dump({}, f)
        return {}

def save_config(config_data):
    global app, ui
    try:
        with open(CONFIG_PATH, 'w') as f: json.dump(config_data, f, indent=4)
    except Exception as e:
        msg = f"Failed to save configuration: {str(e)}"
        final_ui_ref = ui
        if not final_ui_ref and app: final_ui_ref = app.userInterface
        if final_ui_ref: final_ui_ref.messageBox(msg, "Config Error")
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)

def get_fusion_design():
    global app
    try:
        if not app: return None 
        product = app.activeProduct
        return product if product and product.objectType == adsk.fusion.Design.classType() else None
    except: return None

def export_fusion_design(design: adsk.fusion.Design, export_dir: str, base_name: str, formats_to_export: list, target_ui_ref):
    global app
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
                if app: app.log(msg, adsk.core.LogLevels.WarningLogLevel)
                continue

            if options: export_executed_successfully = export_mgr.execute(options)
            
            if export_executed_successfully:
                # Check file existence and size more robustly
                if os.path.exists(full_export_path) and os.path.getsize(full_export_path) > 0:
                    exported_file_paths.append(full_export_path)
                    if app: app.log(f"Exported: {full_export_path}", adsk.core.LogLevels.InfoLogLevel)
                # Some exports might return True but the file creation is async or slightly delayed.
                # For this example, we assume if True is returned, the file should be there.
                # A more robust solution might involve waiting briefly and checking again for some formats.
                elif os.path.exists(full_export_path): # File exists but is empty
                     msg = f"Export reported success for {fmt_lower} but file is empty: {full_export_path}"
                     target_ui_ref.messageBox(msg, CMD_NAME)
                     if app: app.log(msg, adsk.core.LogLevels.WarningLogLevel)
                else: # File does not exist
                    msg = f"Export reported success for {fmt_lower} but file not found: {full_export_path}"
                    target_ui_ref.messageBox(msg, CMD_NAME)
                    if app: app.log(msg, adsk.core.LogLevels.WarningLogLevel)
            elif options: # options were created, but execute returned False or None
                msg = f"Export execution failed or did not confirm success for {fmt_lower}: {full_export_path}"
                target_ui_ref.messageBox(msg, CMD_NAME)
                if app: app.log(msg, adsk.core.LogLevels.WarningLogLevel)

        except Exception as e:
            msg = f"Error exporting {fmt_lower} for '{base_name}':\n{traceback.format_exc()}"
            target_ui_ref.messageBox(msg, CMD_NAME)
            if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
            continue
            
    return exported_file_paths

def handle_git_operations(repo_path, file_basenames_to_add, commit_msg, branch_format_str, target_ui_ref, design_basename_for_branch):
    global app
    repo = None 
    original_branch_name_for_cleanup = None
    stashed_changes_for_cleanup = False
    try:
        repo = Repo(repo_path)
        origin = repo.remotes.origin
        
        if repo.head.is_detached:
            try:
                # Attempt to find the default branch (main or master)
                default_branch_name = "main" # Common default
                if default_branch_name not in repo.branches:
                    if "master" in repo.branches: default_branch_name = "master"
                    else: # Try to get from remote HEAD if possible
                         default_branch_remote_ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD', short=True)
                         default_branch_name = default_branch_remote_ref.split('/')[-1]

                repo.git.checkout(default_branch_name)
                original_branch_name_for_cleanup = default_branch_name
                msg = f"Repo was detached. Switched to '{default_branch_name}'."
                target_ui_ref.messageBox(msg, CMD_NAME)
                if app: app.log(msg, adsk.core.LogLevels.InfoLogLevel)
            except Exception as e_det:
                msg = f"Repo is in detached HEAD and could not switch to default branch: {str(e_det)}. Please resolve manually."
                target_ui_ref.messageBox(msg, CMD_NAME)
                if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
                return None
        else:
            original_branch_name_for_cleanup = repo.active_branch.name
        
        if app: app.log(f"Current branch for operations: {original_branch_name_for_cleanup}", adsk.core.LogLevels.InfoLogLevel)

        if repo.is_dirty(untracked_files=False): # Check for tracked modified files
            repo.git.stash('push', '-u', '-m', 'fusion_git_addin_autostash')
            stashed_changes_for_cleanup = True
            if app: app.log("Stashed local changes.", adsk.core.LogLevels.InfoLogLevel)

        if app: app.log(f"Pulling from origin/{original_branch_name_for_cleanup} with rebase...", adsk.core.LogLevels.InfoLogLevel)
        origin.pull(original_branch_name_for_cleanup, rebase=True) 
        if app: app.log("Pull successful.", adsk.core.LogLevels.InfoLogLevel)

        timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_branch_name = branch_format_str.replace("{timestamp}", timestamp_str).replace("{filename}", design_basename_for_branch)
        new_branch_name = re.sub(r'[^\w\-\./_]+', '_', new_branch_name) # Sanitize branch name

        if app: app.log(f"Creating and checking out new branch: {new_branch_name}", adsk.core.LogLevels.InfoLogLevel)
        new_branch_head = repo.create_head(new_branch_name)
        new_branch_head.checkout()

        if app: app.log(f"Adding files: {', '.join(file_basenames_to_add)}", adsk.core.LogLevels.InfoLogLevel)
        repo.index.add(file_basenames_to_add) 
        
        if app: app.log(f"Committing with message: {commit_msg}", adsk.core.LogLevels.InfoLogLevel)
        repo.index.commit(commit_msg)

        if app: app.log(f"Pushing branch {new_branch_name} to origin...", adsk.core.LogLevels.InfoLogLevel)
        push_info_list = origin.push(new_branch_name, set_upstream=True)
        for push_info in push_info_list:
            if push_info.flags & (push_info.ERROR | push_info.REJECTED):
                err_msg = f"Git push failed for branch '{new_branch_name}': {push_info.summary}"
                target_ui_ref.messageBox(err_msg, CMD_NAME)
                if app: app.log(err_msg, adsk.core.LogLevels.ErrorLogLevel)
                raise GitCommandError(f"Push failed: {push_info.summary}") 
        if app: app.log("Push successful.", adsk.core.LogLevels.InfoLogLevel)
        
        return new_branch_name

    except GitCommandError as e_git:
        msg = f"Git operation failed: {str(e_git)}"
        target_ui_ref.messageBox(msg, CMD_NAME)
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
        return None
    except Exception as e:
        msg = f"Unexpected error during Git operations:\n{traceback.format_exc()}"
        target_ui_ref.messageBox(msg, CMD_NAME)
        if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)
        return None
    finally:
        try:
            if repo and original_branch_name_for_cleanup and repo.active_branch.name != original_branch_name_for_cleanup:
                if app: app.log(f"Attempting to switch back to original branch: {original_branch_name_for_cleanup}", adsk.core.LogLevels.InfoLogLevel)
                repo.git.checkout(original_branch_name_for_cleanup)
            if repo and stashed_changes_for_cleanup:
                if app: app.log("Attempting to pop stashed changes on original branch...", adsk.core.LogLevels.InfoLogLevel)
                repo.git.stash('pop')
                if app: app.log("Stash pop successful on original branch.", adsk.core.LogLevels.InfoLogLevel)
        except GitCommandError as e_cleanup_git:
            cleanup_msg = f"Error during Git cleanup (checkout/stash pop on '{original_branch_name_for_cleanup}'): {str(e_cleanup_git)}"
            if target_ui_ref: target_ui_ref.messageBox(cleanup_msg + "\nPlease check your repository state manually.", CMD_NAME)
            if app: app.log(cleanup_msg, adsk.core.LogLevels.WarningLogLevel)
        except Exception as e_cleanup_general:
            cleanup_msg_gen = f"Unexpected error during Git cleanup: {str(e_cleanup_general)}"
            if app: app.log(cleanup_msg_gen, adsk.core.LogLevels.WarningLogLevel)

# ------------------------------------------------------------------------------
# ADD-IN LIFECYCLE FUNCTIONS: run() and stop()
# ------------------------------------------------------------------------------
def run(context):
    global push_cmd_def, git_push_control, handlers 
    
    # Ensure module-level app and ui are valid
    if not app or not ui:
        try:
            temp_app_run = adsk.core.Application.get()
            if temp_app_run:
                globals()['app'] = temp_app_run 
                globals()['ui'] = temp_app_run.userInterface
            if not globals()['ui']: 
                print("CRITICAL: Could not obtain UserInterface object in run(). Add-in cannot start.")
                if globals()['app']: globals()['app'].log("CRITICAL: Could not obtain UserInterface object in run().", adsk.core.LogLevels.CriticalLogLevel)
                return
        except Exception as e_init_run:
            print(f"CRITICAL: Exception while re-getting app/ui in run(): {traceback.format_exc()}")
            return

    try:
        handlers.clear() 

        push_cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if not push_cmd_def:
            push_cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, "") 

        on_cmd_created = GitCommandCreatedEventHandler()
        push_cmd_def.commandCreated.add(on_cmd_created)
        handlers.append(on_cmd_created)

        target_panel = ui.allToolbarPanels.itemById(PANEL_ID)
        if app and target_panel: app.log(f"Primary panel '{PANEL_ID}' found: {target_panel.name if target_panel else 'No'}", adsk.core.LogLevels.InfoLogLevel)

        if not target_panel:
            if app: app.log(f"Primary panel '{PANEL_ID}' not found. Trying fallbacks.", adsk.core.LogLevels.InfoLogLevel)
            design_workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if design_workspace:
                possible_fallback_ids = [FALLBACK_PANEL_ID, "ToolsSolidPythonScriptsPanel", "FusionSolidScriptPanel"]
                for panel_id_option in possible_fallback_ids:
                    tb_panel_candidate = design_workspace.toolbarPanels.itemById(panel_id_option)
                    if tb_panel_candidate:
                        target_panel = tb_panel_candidate
                        if app: app.log(f"Found fallback panel: '{target_panel.id}' ({target_panel.name})", adsk.core.LogLevels.InfoLogLevel)
                        break
            if not target_panel and app: app.log(f"No suitable fallback panel found in Design workspace.", adsk.core.LogLevels.WarningLogLevel)
        
        if target_panel:
            if app: app.log(f"Target panel '{target_panel.id if target_panel else 'None'}' is being used. Attempting to add/find control '{CONTROL_ID}'.", adsk.core.LogLevels.InfoLogLevel)
            
            git_push_control = target_panel.controls.itemById(CONTROL_ID) 
            if git_push_control and git_push_control.isValid: 
                if app: app.log(f"Command control '{CONTROL_ID}' already exists in panel '{target_panel.id}'. Re-using.", adsk.core.LogLevels.InfoLogLevel)
            else: 
                git_push_control = target_panel.controls.addCommand(push_cmd_def, CONTROL_ID) 
                if app: app.log(f"New command control '{CONTROL_ID}' {'created successfully' if git_push_control and git_push_control.isValid else 'FAILED to create'}.", adsk.core.LogLevels.InfoLogLevel)
            
            if git_push_control and git_push_control.isValid:
                git_push_control.isPromotedByDefault = True 
                git_push_control.isPromoted = True        
                git_push_control.isVisible = True         
                if app: app.log(f"Command control '{CONTROL_ID}' configured for visibility in panel '{target_panel.id}'.", adsk.core.LogLevels.InfoLogLevel)
            else:
                if app: app.log(f"Command control '{CONTROL_ID}' is None or invalid in panel '{target_panel.id}'. Button not visible.", adsk.core.LogLevels.ErrorLogLevel)
        else:
            msg = f"Could not find any target panel ('{PANEL_ID}' or fallbacks) to add the '{CMD_NAME}' button."
            if ui: ui.messageBox(msg, "Add-In UI Error")
            if app: app.log(msg, adsk.core.LogLevels.ErrorLogLevel)

        adsk.autoTerminate(False)
        if app: app.log(f"'{CMD_NAME}' Add-In Loaded and running.", adsk.core.LogLevels.InfoLogLevel)

    except:
        error_msg = 'Failed to run the Add-In (run function):\n{}'.format(traceback.format_exc())
        if ui: ui.messageBox(error_msg, CMD_NAME + " - Critical Error")
        if app: app.log(error_msg, adsk.core.LogLevels.CriticalLogLevel)
        adsk.autoTerminate(True)


def stop(context):
    global push_cmd_def, git_push_control, handlers 
    
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
                if current_app_ref: current_app_ref.log("CRITICAL: Could not obtain UserInterface in stop().", adsk.core.LogLevels.CriticalLogLevel)
                return
        except Exception:
            print(f"CRITICAL: Exception while re-getting app/ui in stop(): {traceback.format_exc()}")
            return
    try:
        if git_push_control and git_push_control.isValid:
            git_push_control.deleteMe()
        
        if push_cmd_def and push_cmd_def.isValid:
            push_cmd_def.deleteMe()

        handlers.clear() 

        if current_app_ref: current_app_ref.log(f"'{CMD_NAME}' Add-In Stopped.", adsk.core.LogLevels.InfoLogLevel)

    except:
        error_msg = 'Failed to stop the Add-In cleanly (stop function):\n{}'.format(traceback.format_exc())
        if current_ui_ref: current_ui_ref.messageBox(error_msg, CMD_NAME + " - Stop Error")
        if current_app_ref: current_app_ref.log(error_msg, adsk.core.LogLevels.ErrorLogLevel)
