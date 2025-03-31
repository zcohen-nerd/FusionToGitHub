import adsk.core, adsk.fusion, traceback
import os, shutil, re, json
from git import Repo, GitCommandError
from datetime import datetime
from urllib.parse import urlparse
import subprocess

# Set Git executable path (modify if needed)
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\\Program Files\\Git\\cmd\\git.exe"

# Constants
CONFIG_PATH = os.path.expanduser("~/.fusion_git_repos.json")
REPO_BASE_DIR = os.path.expanduser("~/FusionGitRepos")
ADD_NEW_OPTION = "➕ Add new GitHub repo..."

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion design", "Error")
            return

        # Load or create config
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'w') as f:
                json.dump({}, f)

        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

        repo_names = list(config.keys())
        repo_names.append(ADD_NEW_OPTION)

        # Prompt user to select or add repo
        selected = ui.inputBox("Select GitHub project to push to:\n" +
                               "\n".join(repo_names), "Select Project", repo_names[0])[0]

        if selected == ADD_NEW_OPTION:
            git_url = ui.inputBox("Enter full GitHub repo URL:", "New Repo URL")[0].strip()
            if not git_url.endswith(".git"):
                ui.messageBox("URL must end in .git")
                return

            repo_name = os.path.splitext(os.path.basename(urlparse(git_url).path))[0]
            local_path = os.path.join(REPO_BASE_DIR, repo_name)

            if not os.path.exists(local_path):
                os.makedirs(REPO_BASE_DIR, exist_ok=True)
                subprocess.run(["git", "clone", git_url, local_path], check=True)

            config[repo_name] = {"url": git_url, "path": local_path}
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)

            selected_repo = config[repo_name]
        else:
            if selected not in config:
                ui.messageBox(f"'{selected}' not found in config.")
                return
            selected_repo = config[selected]

        git_repo_path = os.path.expanduser(selected_repo["path"])
        temp_dir = os.path.join(git_repo_path, "temp")

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Clean filename
        raw_name = design.rootComponent.name
        clean_name = re.sub(r' v\\d+$', '', raw_name)
        filename = f"{clean_name}.f3d"
        export_path = os.path.join(temp_dir, filename)

        # Export Fusion file
        export_mgr = design.exportManager
        options = export_mgr.createFusionArchiveExportOptions(export_path)
        export_mgr.execute(options)

        if not os.path.exists(export_path):
            ui.messageBox("Export failed.")
            return

        # Prompt for commit message
        commit_message = ui.inputBox("Enter a commit message:", "Commit", "Updated design")[0].strip()
        if not commit_message:
            ui.messageBox("Commit message cannot be empty.")
            return

        # Copy to Git repo
        shutil.copy2(export_path, git_repo_path)

        # Git operations
        repo = Repo(git_repo_path)

        if repo.head.is_detached:
            ui.messageBox("Git repo is in a detached HEAD state.")
            return

        rebase_path = os.path.join(git_repo_path, ".git", "rebase-merge")
        if os.path.exists(rebase_path):
            ui.messageBox("Unfinished rebase detected. Resolve manually.")
            return

        # Create and checkout new branch
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        branch_name = f"fusion-auto-{timestamp}"
        repo.git.checkout("-b", branch_name)

        # Remove older .f3d versions with same prefix
        for f in os.listdir(git_repo_path):
            if f.endswith(".f3d") and f.startswith(clean_name) and f != filename:
                try:
                    os.remove(os.path.join(git_repo_path, f))
                    repo.git.rm(f)
                except Exception:
                    pass

        repo.git.add(filename)
        repo.index.commit(commit_message)

        try:
            repo.git.push("--set-upstream", "origin", branch_name)
        except GitCommandError as e:
            ui.messageBox(f"Git push failed:\n{str(e)}")
            return

        ui.messageBox(f"✅ Pushed to branch: {branch_name}\nOpen a pull request on GitHub to merge.")
        shutil.rmtree(temp_dir)

    except Exception as e:
        ui.messageBox("Script error:\n" + traceback.format_exc())

    adsk.autoTerminate(True)
