import adsk.core, adsk.fusion, traceback
import os, shutil, re
from git import Repo
from datetime import datetime

# Set Git executable path (edit if needed)
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r"C:\Program Files\Git\cmd\git.exe"

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox('No active Fusion design', 'Error')
            return

        # Prompt for commit message
        commit_input = ui.inputBox("Enter a commit message for GitHub:", "Commit Message", "Updated design")[0]
        if not commit_input or not commit_input.strip():
            ui.messageBox("Commit message cannot be empty.")
            return

        # Paths (customize these)
        git_repo_path = os.path.expanduser(r"C:\path\to\your\local\repo")
        temp_dir = os.path.expanduser(r"C:\temp\FusionExport")

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Clean version number from filename (e.g., remove " v42")
        raw_name = design.rootComponent.name
        clean_name = re.sub(r' v\d+$', '', raw_name)
        filename = f"{clean_name}.f3d"
        export_path = os.path.join(temp_dir, filename)

        # Export Fusion file
        export_mgr = design.exportManager
        options = export_mgr.createFusionArchiveExportOptions(export_path)
        export_mgr.execute(options)

        if not os.path.exists(export_path):
            ui.messageBox('Export failed.')
            return

        # Copy to Git repo
        shutil.copy2(export_path, git_repo_path)

        # Git operations
        repo = Repo(git_repo_path)

        # Check for unfinished rebase
        rebase_path = os.path.join(git_repo_path, '.git', 'rebase-merge')
        if os.path.exists(rebase_path):
            ui.messageBox("Git is stuck in an unfinished rebase. Please resolve it manually:\n\n"
                          " - git rebase --abort\n"
                          " - OR git rebase --continue\n"
                          " - OR delete .git/rebase-merge if safe")
            return

        if repo.head.is_detached:
            ui.messageBox('Git repo is in a detached HEAD state. Please check out a branch manually before running this script.')
            return

        # Create a new branch for this push
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M')
        branch_name = f"fusion-auto-{timestamp}"
        repo.git.checkout('-b', branch_name)

        repo.git.add(filename)
        repo.index.commit(commit_input.strip())

        try:
            repo.git.push('--set-upstream', 'origin', branch_name)
        except Exception as push_error:
            ui.messageBox(f'Git push failed:\n{str(push_error)}')
            return

        ui.messageBox(f'Successfully pushed to branch \"{branch_name}\".\n\n"
                      "Please open a Pull Request on GitHub to merge your changes into main.")
        shutil.rmtree(temp_dir)

    except Exception as e:
        ui.messageBox(f'Script error:\n{traceback.format_exc()}')

    adsk.autoTerminate(True)
