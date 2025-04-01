import adsk.core, adsk.fusion, adsk.cam, traceback
import os, shutil, re, json
from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime
from urllib.parse import urlparse
import subprocess

# Set Git executable path
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"

CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")
ADD_NEW_OPTION = "+ Add new GitHub repo..."
EDIT_EXISTING_OPTION = "⚙ Edit settings for existing repo..."

handlers = []

class GitCommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        app = adsk.core.Application.get()
        ui = app.userInterface
        config = load_config()
        repo_names = list(config.keys()) + [ADD_NEW_OPTION, EDIT_EXISTING_OPTION]

        args.command.isAutoTerminate = True
        inputs = args.command.commandInputs
        dropdown_input = inputs.addDropDownCommandInput("repoSelector", "Select Repo", adsk.core.DropDownStyles.TextListDropDownStyle)
        for name in repo_names:
            dropdown_input.listItems.add(name, name == repo_names[0])

        commit_input = inputs.addStringValueInput("commitMsg", "Commit Message", "Updated design")

        class ExecuteHandler(adsk.core.CommandEventHandler):
            def notify(self, execute_args):
                selected_repo_name = dropdown_input.selectedItem.name

                if selected_repo_name == ADD_NEW_OPTION:
                    git_url = ui.inputBox("GitHub repo URL:", "New Repo")[0].strip()
                    if not git_url.endswith(".git"):
                        ui.messageBox("URL must end in .git")
                        return

                    repo_name = os.path.splitext(os.path.basename(urlparse(git_url).path))[0]
                    local_path = os.path.join(REPO_BASE_DIR, repo_name)

                    os.makedirs(REPO_BASE_DIR, exist_ok=True)
                    subprocess.run(["git", "clone", git_url, local_path], check=True)

                    config[repo_name] = {
                        "url": git_url,
                        "path": local_path,
                        **prompt_repo_settings(ui)
                    }
                    save_config(config)
                    selected_repo = config[repo_name]

                elif selected_repo_name == EDIT_EXISTING_OPTION:
                    repo_names_only = list(config.keys())
                    repo_to_edit = ui.inputBox("Repo to edit:\n" + "\n".join(repo_names_only), "Edit Repo", repo_names_only[0])[0]
                    if repo_to_edit not in config:
                        ui.messageBox("Repo not found.")
                        return
                    config[repo_to_edit].update(prompt_repo_settings(ui, config[repo_to_edit]))
                    save_config(config)
                    return
                else:
                    selected_repo = config[selected_repo_name]

                if not check_git_available(ui):
                    return

                design = get_fusion_design()
                if not design:
                    ui.messageBox("No active Fusion design.")
                    return

                raw_name = design.rootComponent.name
                clean_name = re.sub(r' v\d+$', '', raw_name)
                filename = f"{clean_name}.f3d"
                git_repo_path = os.path.expanduser(selected_repo["path"])
                temp_dir = os.path.join(git_repo_path, "temp")
                os.makedirs(temp_dir, exist_ok=True)
                export_path = os.path.join(temp_dir, filename)

                export_fusion_design(design, export_path)
                commit_message = commit_input.value.strip() or selected_repo.get("defaultMessage", "Updated design")
                copy_to_git_repo(export_path, git_repo_path)

                branch_name = handle_git_operations(
                    git_repo_path, filename, commit_message,
                    selected_repo.get("branchFormat", "fusion-auto-{timestamp}"), ui)

                if branch_name:
                    ui.messageBox(f"✅ Pushed to branch: {branch_name}\nCreate a pull request to merge.")

                shutil.rmtree(temp_dir)

        on_execute = ExecuteHandler()
        args.command.execute.add(on_execute)
        handlers.append(on_execute)

def check_git_available(ui):
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        ui.messageBox("Git not found. Install it from https://git-scm.com/downloads", "Git Not Found")
        return False

def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({}, f)
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def prompt_repo_settings(ui, existing_config=None):
    export_formats = ui.inputBox("Export formats (e.g., f3d,step,stl):", "Export Formats", ",".join(existing_config.get("exportFormats", ["f3d"])) if existing_config else "f3d")[0].strip()
    default_message = ui.inputBox("Default commit message:", "Commit Message", existing_config.get("defaultMessage", "Updated design") if existing_config else "Updated design")[0].strip()
    branch_format = ui.inputBox("Branch naming format (use {timestamp}):", "Branch Format", existing_config.get("branchFormat", "fusion-auto-{timestamp}") if existing_config else "fusion-auto-{timestamp}")[0].strip()
    return {
        "exportFormats": [f.strip().lower() for f in export_formats.split(",")],
        "defaultMessage": default_message,
        "branchFormat": branch_format
    }

def get_fusion_design():
    app = adsk.core.Application.get()
    design = app.activeProduct
    if isinstance(design, adsk.fusion.Design):
        return design
    return None

def export_fusion_design(design, export_path):
    export_mgr = design.exportManager
    options = export_mgr.createFusionArchiveExportOptions(export_path)
    export_mgr.execute(options)

def copy_to_git_repo(export_path, git_repo_path):
    shutil.copy2(export_path, git_repo_path)

def handle_git_operations(git_repo_path, filename, commit_message, branch_format, ui):
    try:
        repo = Repo(git_repo_path)
    except InvalidGitRepositoryError:
        ui.messageBox("Invalid Git repository.")
        return None

    if repo.head.is_detached:
        ui.messageBox("Git repo is in a detached HEAD state.")
        return None

    rebase_path = os.path.join(git_repo_path, ".git", "rebase-merge")
    if os.path.exists(rebase_path):
        ui.messageBox("Unfinished rebase detected. Resolve manually.")
        return None

    branch_name = branch_format.replace("{timestamp}", datetime.now().strftime("%Y-%m-%d-%H%M"))
    repo.git.checkout("-b", branch_name)

    for f in os.listdir(git_repo_path):
        if f.endswith(".f3d") and f.startswith(filename.split('.')[0]) and f != filename:
            try:
                os.remove(os.path.join(git_repo_path, f))
                repo.git.rm(f)
            except:
                pass

    repo.git.add(filename)
    repo.index.commit(commit_message)
    repo.git.push("--set-upstream", "origin", branch_name)

    return branch_name

def run(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        cmd_defs = ui.commandDefinitions
        push_cmd = cmd_defs.itemById("FusionGitPush") or cmd_defs.addButtonDefinition("FusionGitPush", "Push Fusion to GitHub", "Push active design to a GitHub repo")

        cmd_created_handler = GitCommandCreatedEventHandler()
        push_cmd.commandCreated.add(cmd_created_handler)
        handlers.append(cmd_created_handler)

        push_cmd.execute()
        adsk.autoTerminate(False)
        

    except Exception as e:
        app = adsk.core.Application.get()
        ui = app.userInterface
        ui.messageBox(f"Script error:\n{traceback.format_exc()}")
