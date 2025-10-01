"""
Diagnostic Script for FusionToGitHub Add-In
Run this to help diagnose why the add-in might be crashing silently.
"""

import os
import sys

print("=" * 70)
print("FusionToGitHub Add-In Diagnostic Tool")
print("=" * 70)

# 1. Check Python version
print(f"\n1. Python Version: {sys.version}")
print(f"   Python Executable: {sys.executable}")

# 2. Check if Git is available
import shutil
git_exe = shutil.which("git")
if git_exe:
    print(f"\n2. Git Found: {git_exe}")
    import subprocess
    try:
        result = subprocess.run([git_exe, "--version"], capture_output=True, text=True)
        print(f"   Version: {result.stdout.strip()}")
    except Exception as e:
        print(f"   Error running git: {e}")
else:
    print("\n2. Git NOT FOUND in PATH")

# 3. Check log file
log_path = os.path.expanduser("~/.PushToGitHub_AddIn_Data/PushToGitHub.log")
print(f"\n3. Log File: {log_path}")
if os.path.exists(log_path):
    print(f"   File exists (size: {os.path.getsize(log_path)} bytes)")
    print("\n   Last 20 lines of log:")
    print("   " + "-" * 66)
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(f"   {line.rstrip()}")
    except Exception as e:
        print(f"   Error reading log: {e}")
else:
    print("   Log file does not exist yet")

# 4. Check if source files exist
src_dir = os.path.dirname(os.path.abspath(__file__))
print(f"\n4. Source Directory: {src_dir}")
files_to_check = [
    "Push_To_GitHub.py",
    "Push_To_GitHub.manifest",
    "fusion_git_core.py",
    "push_cli.py"
]
for filename in files_to_check:
    filepath = os.path.join(src_dir, filename)
    if os.path.exists(filepath):
        print(f"   ✓ {filename} (size: {os.path.getsize(filepath)} bytes)")
    else:
        print(f"   ✗ {filename} MISSING")

# 5. Try importing the core module
print("\n5. Testing imports:")
try:
    sys.path.insert(0, src_dir)
    import fusion_git_core
    print(f"   ✓ fusion_git_core imported successfully (Version: {fusion_git_core.VERSION})")
except Exception as e:
    print(f"   ✗ Failed to import fusion_git_core: {e}")

# 6. Check for syntax errors in main file
print("\n6. Checking for syntax errors:")
main_file = os.path.join(src_dir, "Push_To_GitHub.py")
try:
    with open(main_file, 'r', encoding='utf-8') as f:
        code = f.read()
    compile(code, main_file, 'exec')
    print(f"   ✓ No syntax errors in Push_To_GitHub.py")
except SyntaxError as e:
    print(f"   ✗ Syntax Error: {e}")
    print(f"      Line {e.lineno}: {e.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# 7. Check config file
config_path = os.path.expanduser("~/.fusion_git_repos.json")
print(f"\n7. Config File: {config_path}")
if os.path.exists(config_path):
    print(f"   File exists (size: {os.path.getsize(config_path)} bytes)")
    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"   ✓ Valid JSON (repositories configured: {len([k for k in config.keys() if k != '__meta__'])})")
    except Exception as e:
        print(f"   ✗ Invalid JSON: {e}")
else:
    print("   Config file does not exist (will be created on first use)")

print("\n" + "=" * 70)
print("Diagnostic Complete!")
print("=" * 70)
print("\nNext Steps:")
print("1. If log file shows errors, read the error messages carefully")
print("2. If syntax errors found, fix them before loading in Fusion")
print("3. Try restarting Fusion 360 completely")
print("4. Check Fusion's Text Commands window for error messages")
print("5. In Fusion: Scripts and Add-Ins > select add-in > click 'Run'")
print("=" * 70)
