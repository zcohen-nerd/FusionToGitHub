import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json
from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime
from urllib.parse import urlparse
import subprocess

# ------------------------------------------------------------------------------
# GIT CONFIGURATION
# ------------------------------------------------------------------------------
# This environment variable tells GitPython where to find the 'git' executable.
# Make sure Git is installed and this path is correct:
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"

# ------------------------------------------------------------------------------
# SCRIPT-WIDE CONSTANTS
# ------------------------------------------------------------------------------
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")  # Where repo settings are stored
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")        # Local base folder for cloned repos

ADD_NEW_OPTION = "+ Add new GitHub repo..."                   # Dropdown UI option
EDIT_EXISTING_OPTION = "⚙ Edit settings for existing repo..." # Dropdown UI option

handlers = []  # Keep references to event handlers to prevent garbage collection

# ------------------------------------------------------------------------------
# EVENT HANDLER: CREATES THE COMMAND UI
# ------------------------------------------------------------------------------
class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    """
    Triggered when our custom Fusion command is created.
    Sets up the UI for selecting a repo, commit message, etc.
    """
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Load user config (local JSON)
        config = load_config()

        # Create a list of existing repos, plus special options for add/edit
        repo_names = list(config.keys()) + [ADD_NEW_OPTION, EDIT_EXISTING_OPTION]

        # Basic command UI properties
        args.command.isAutoTerminate = True
        inputs = args.command.commandInputs

        # ------------------------------------------------------------------------------
        # CREATE DROPDOWN FOR REPO SELECTION
        # ------------------------------------------------------------------------------
        dropdown_input = inputs.addDropDownCommandInput(
            "repoSelector",
            "Select Repo",
            adsk.core.DropDownStyles.TextListDropDownStyle
        )
        for name in repo_names:
            # Mark the first item as default
            dropdown_input.listItems.add(name, name == repo_names[0])

        # ------------------------------------------------------------------------------
        # COMMIT MESSAGE INPUT
        # ------------------------------------------------------------------------------
        commit_input = inputs.addStringValueInput(
            "commitMsg",
            "Commit Message",
            "Updated design"
        )

        # ------------------------------------------------------------------------------
        # EXECUTE HANDLER: RUNS WHEN USER HITS "OK"
        # ------------------------------------------------------------------------------
        class ExecuteHandler(adsk.core.CommandEventHandler):
            def notify(self, execute_args):
                selected_repo_name = dropdown_input.selectedItem.name

                # 1) USER SELECTED: ADD NEW REPO
                if selected_repo_name == ADD_NEW_OPTION:
                    git_url = ui.inputBox("GitHub repo URL:", "New Repo")[0].strip()
                    if not git_url.endswith(".git"):
                        ui.messageBox("URL must end in .git")
                        return

                    repo_name = os.path.splitext(os.path.basename(urlparse(git_url).path))[0]
                    local_path = os.path.join(REPO_BASE_DIR, repo_name)

                    # Clone the new repo from GitHub
                    os.makedirs(REPO_BASE_DIR, exist_ok=True)
                    subprocess.run(["git", "clone", git_url, local_path], check=True)

                    # Prompt user for formats, default message, etc.
                    config[repo_name] = {
                        "url": git_url,
                        "path": local_path,
                        **prompt_repo_settings(ui)
                    }
                    save_config(config)
                    selected_repo = config[repo_name]

                # 2) USER SELECTED: EDIT REPO SETTINGS
                elif selected_repo_name == EDIT_EXISTING_OPTION:
                    repo_names_only = list(config.keys())
                    repo_to_edit = ui.inputBox(
                        "Repo to edit:\n" + "\n".join(repo_names_only),
                        "Edit Repo",
                        repo_names_only[0]
                    )[0]
                    if repo_to_edit not in config:
                        ui.messageBox("Repo not found.")
                        return

                    # Update existing settings
                    config[repo_to_edit].update(prompt_repo_settings(ui, config[repo_to_edit]))
                    save_config(config)
                    selected_repo = config[repo_to_edit]

                # 3) USER SELECTED AN EXISTING REPO
                else:
                    selected_repo = config[selected_repo_name]

                # Check that Git is installed
                if not check_git_available(ui):
                    return

                # Ensure we have an active Fusion design
                design = get_fusion_design()
                if not design:
                    ui.messageBox("No active Fusion design.")
                    return

                # Clean the base filename
                raw_name = design.rootComponent.name
                clean_name = re.sub(r' v\d+$', '', raw_name)
                base_name = clean_name

                # Setup local directories
                git_repo_path = os.path.expanduser(selected_repo["path"])
                temp_dir = os.path.join(git_repo_path, "temp")
                os.makedirs(temp_dir, exist_ok=True)

                # Determine which formats to export
                export_formats = selected_repo.get("exportFormats", ["f3d"])
                # Perform the actual export
                exported_files = export_fusion_design(design, temp_dir, base_name, export_formats, ui)

                # Copy exported files to local repo
                commit_message = commit_input.value.strip() or selected_repo.get("defaultMessage", "Updated design")
                for file in exported_files:
                    copy_to_git_repo(file, git_repo_path)

                # Build list of file names
                filenames = [os.path.basename(f) for f in exported_files]

                # Actually do the Git commit/push
                branch_name = handle_git_operations(
                    git_repo_path,
                    filenames,
                    commit_message,
                    selected_repo.get("branchFormat", "fusion-auto-{timestamp}"),
                    ui
                )

                # If successful, show success message
                if branch_name:
                    ui.messageBox(f"✅ Pushed to branch: {branch_name}\nCreate a pull request to merge.")

                # Cleanup temporary export folder
                shutil.rmtree(temp_dir)

        # Create an instance of our execution handler
        on_execute = ExecuteHandler()
        args.command.execute.add(on_execute)
        handlers.append(on_execute)

# ------------------------------------------------------------------------------
# CHECK GIT INSTALLATION
# ------------------------------------------------------------------------------
def check_git_available(ui):
    """
    Runs 'git --version' to ensure Git is in PATH and installed.
    """
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        ui.messageBox("Git not found. Install it from https://git-scm.com/downloads", "Git Not Found")
        return False

# ------------------------------------------------------------------------------
# LOAD AND SAVE CONFIG
# ------------------------------------------------------------------------------
def load_config():
    """
    Load repository settings from JSON at CONFIG_PATH.
    If none found, create an empty JSON.
    """
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({}, f)
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    """
    Write updated repo settings to JSON.
    """
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

# ------------------------------------------------------------------------------
# PROMPT USER FOR REPO SETTINGS
# ------------------------------------------------------------------------------
def prompt_repo_settings(ui, existing_config=None):
    """
    Ask user for which formats to export, default commit message, and branch naming.
    """
    export_formats_input = ui.inputBox(
        "Export formats (e.g., f3d, step, stl, dwg, dxf):",
        "Export Formats",
        ",".join(existing_config.get("exportFormats", ["f3d"])) if existing_config else "f3d"
    )[0].strip()

    default_message = ui.inputBox(
        "Default commit message:",
        "Commit Message",
        existing_config.get("defaultMessage", "Updated design") if existing_config else "Updated design"
    )[0].strip()

    branch_format = ui.inputBox(
        "Branch naming format (use {timestamp}):",
        "Branch Format",
        existing_config.get("branchFormat", "fusion-auto-{timestamp}") if existing_config else "fusion-auto-{timestamp}"
    )[0].strip()

    return {
        "exportFormats": [f.strip().lower() for f in export_formats_input.split(",")],
        "defaultMessage": default_message,
        "branchFormat": branch_format
    }

# ------------------------------------------------------------------------------
# GET CURRENT DESIGN
# ------------------------------------------------------------------------------
def get_fusion_design():
    """
    Retrieves the currently open Design workspace in Fusion (or None if none).
    """
    app = adsk.core.Application.get()
    design = app.activeProduct
    if isinstance(design, adsk.fusion.Design):
        return design
    return None

# ------------------------------------------------------------------------------
# EXPORT FUSION DESIGN
# ------------------------------------------------------------------------------
def export_fusion_design(design, export_dir, base_name, formats=["f3d"], ui=None):
    """
    Export the current design to multiple formats: f3d, step, stl, dwg, dxf
    (depending on version). Returns a list of file paths created.
    """
    export_mgr = design.exportManager
    exported_files = []

    # Helper: gather all visible, solid bodies (for STL)
    def get_all_bodies(component):
        bodies = []
        for body in component.bRepBodies:
            if body.isSolid and body.isVisible:
                bodies.append(body)
        for occ in component.occurrences:
            bodies += get_all_bodies(occ.component)
        return bodies

    for fmt in formats:
        fmt = fmt.lower()
        export_file = os.path.join(export_dir, f"{base_name}.{fmt}")

        if ui:
            ui.messageBox(f"Attempting to export {fmt.upper()} to: {export_file}")

        try:
            # Decide which export options
            if fmt == "f3d":
                options = export_mgr.createFusionArchiveExportOptions(export_file)
            elif fmt == "step":
                options = export_mgr.createSTEPExportOptions(export_file)
                options.isComponentSelection = False
            elif fmt == "stl":
                bodies = get_all_bodies(design.rootComponent)
                if not bodies:
                    if ui:
                        ui.messageBox("No visible solid bodies found for STL export.")
                    continue
                options = export_mgr.createSTLExportOptions(bodies[0], export_file)
                options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
                options.isBinaryFormat = True
            elif fmt == "dwg":
                if hasattr(export_mgr, 'createDWGExportOptions'):
                    # For 2D drawings
                    options = export_mgr.createDWGExportOptions(export_file, design.rootComponent)
                else:
                    if ui:
                        ui.messageBox("DWG export not supported in this Fusion version.")
                    continue
            elif fmt == "dxf":
                if hasattr(export_mgr, 'createDXFExportOptions'):
                    # For 2D drawings
                    options = export_mgr.createDXFExportOptions(export_file, design.rootComponent)
                else:
                    if ui:
                        ui.messageBox("DXF export not supported in this Fusion version.")
                    continue
            else:
                if ui:
                    ui.messageBox(f"Unsupported format: {fmt}")
                continue

            # Perform the actual export
            export_mgr.execute(options)

            # Verify file creation
            if os.path.exists(export_file):
                exported_files.append(export_file)
            else:
                raise Exception("File was not created.")

        except Exception as export_error:
            if ui:
                ui.messageBox(f"[{fmt.upper()}] Export failed:\n{export_error}\nTarget: {export_file}")
            continue

    return exported_files

# ------------------------------------------------------------------------------
# COPY EXPORT TO REPO
# ------------------------------------------------------------------------------
def copy_to_git_repo(export_path, git_repo_path):
    """
    Copy a local export file into the Git working directory.
    """
    shutil.copy2(export_path, git_repo_path)

# ------------------------------------------------------------------------------
# HANDLE GIT OPERATIONS
# ------------------------------------------------------------------------------
def handle_git_operations(git_repo_path, filenames, commit_message, branch_format, ui):
    """
    1) Pull the latest from remote so local has all existing files.
    2) Create a new branch.
    3) Stage & commit only the newly exported files.
    4) Push the changes to remote.
    """
    try:
        repo = Repo(git_repo_path)
    except InvalidGitRepositoryError:
        ui.messageBox("Invalid Git repository.")
        return None

    if repo.head.is_detached:
        ui.messageBox("Git repo is in a detached HEAD state.")
        return None

    # Attempt to pull existing remote data
    try:
        repo.git.pull('--rebase', '--autostash')
    except Exception as e:
        ui.messageBox(f"Git pull (rebase) failed:\n{str(e)}\nPlease resolve conflicts manually.")
        return None

    # Create a new branch name using timestamp
    branch_name = branch_format.replace("{timestamp}", datetime.now().strftime("%Y-%m-%d-%H%M"))

    # Attempt to checkout new branch
    try:
        repo.git.checkout("-b", branch_name)
    except GitCommandError as e:
        ui.messageBox(f"Couldn't create branch:\n{str(e)}")
        return None

    # Stage only newly exported files
    for fn in filenames:
        try:
            repo.git.add(fn)
        except Exception as e:
            ui.messageBox(f"Failed to stage {fn}:\n{e}")

    # Commit
    repo.index.commit(commit_message)

    # Push to remote
    try:
        repo.git.push("--set-upstream", "origin", branch_name)
    except GitCommandError as e:
        ui.messageBox(f"Git push failed:\n{str(e)}")
        return None

    return branch_name

# ------------------------------------------------------------------------------
# SCRIPT ENTRY POINT
# ------------------------------------------------------------------------------
def run(context):
    """
    This run() function is called when the script is executed from Fusion's Add-Ins.
    It sets up a new command or reuses an existing button to push changes to GitHub.
    """
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
    except:
        app, ui = None, None

    try:
        if not app or not ui:
            raise RuntimeError("Fusion application or UI could not be initialized.")

        # Create or retrieve the push command definition
        cmd_defs = ui.commandDefinitions
        push_cmd = cmd_defs.itemById("FusionGitPush")
        if not push_cmd:
            push_cmd = cmd_defs.addButtonDefinition(
                "FusionGitPush",
                "Push Fusion to GitHub",
                "Push active design to a GitHub repo"
            )

        # Attach our event handler
        cmd_created_handler = GitCommandCreatedEventHandler()
        push_cmd.commandCreated.add(cmd_created_handler)
        handlers.append(cmd_created_handler)

        # Execute the command immediately
        push_cmd.execute()
        adsk.autoTerminate(False)

    except Exception as e:
        if ui:
            ui.messageBox(f"Script error:\n{traceback.format_exc()}")
        else:
            print("Fusion UI not available.")
            print(traceback.format_exc())
