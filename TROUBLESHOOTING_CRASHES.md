# Troubleshooting Silent Crashes in Fusion 360

## Issue Fixed: Import Order Problem

**Root Cause:** The refactored code moved `adsk.core`, `adsk.fusion`, and `adsk.cam` imports to the top of the file. These modules are only available when Fusion 360 is fully initialized, so importing them at module load time causes a silent crash.

**Solution Applied:** Wrapped the Fusion API imports in a try-except block:

```python
# Fusion 360 API imports - these must be imported after Fusion is initialized
try:
    import adsk.core
    import adsk.fusion
    import adsk.cam
except ImportError:
    # This is expected when running outside Fusion 360 (e.g., for linting)
    pass
```

## Diagnostic Steps to Follow

### 1. Check the Log File (Most Important!)

```powershell
Get-Content "$env:USERPROFILE\.PushToGitHub_AddIn_Data\PushToGitHub.log" -Tail 50
```

Or run the diagnostic script:
```powershell
python "c:\Users\ZCohe\OneDrive\Documents\Python Scripts\Fusion_to_GitHub\FusionToGitHub\src\diagnostic.py"
```

### 2. Reload the Add-In in Fusion 360

1. **Stop the add-in** (if it's running):
   - Go to: `Scripts and Add-Ins` (Shift+S)
   - Select "Push to GitHub (ZAC)"
   - Click "Stop"

2. **Restart Fusion 360 completely** (important!)
   - Close Fusion
   - Reopen Fusion

3. **Run the add-in**:
   - Go to: `Scripts and Add-Ins` (Shift+S)
   - Go to "Add-Ins" tab
   - Select "Push to GitHub (ZAC)"
   - Click "Run"
   - Check the box "Run on Startup" (optional)

### 3. Check for Errors in Fusion's Text Commands Window

- Open Text Commands: View > Text Commands
- Look for any Python errors or exceptions

### 4. Common Silent Crash Causes

#### A. Import Errors
- **Symptom**: Add-in doesn't show up in toolbar
- **Solution**: Fixed by wrapping adsk imports in try-except
- **Check**: Run `diagnostic.py` to verify no syntax errors

#### B. Missing Dependencies
- **Symptom**: ImportError for fusion_git_core
- **Solution**: Ensure `fusion_git_core.py` is in the same directory
- **Check**: All files must be in Fusion's add-ins directory

#### C. API Changes
- **Symptom**: AttributeError when accessing Fusion objects
- **Solution**: Check if Fusion API has changed (rare)
- **Check**: Look for errors in log file

#### D. Configuration File Corruption
- **Symptom**: JSON decode error in logs
- **Solution**: Delete `~/.fusion_git_repos.json` (will be recreated)
- **Check**: Run `diagnostic.py` to verify JSON is valid

### 5. Enable Debug Logging

The add-in already has comprehensive logging. To see more details:

1. Open the dialog
2. Change log level to "DEBUG"
3. Try the operation again
4. Check the log file

### 6. Fresh Install Steps

If all else fails, do a clean reinstall:

1. **Remove the add-in**:
   ```powershell
   Remove-Item "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\PushToGitHub" -Recurse -Force
   ```

2. **Clear config**:
   ```powershell
   Remove-Item "$env:USERPROFILE\.fusion_git_repos.json" -Force
   Remove-Item "$env:USERPROFILE\.PushToGitHub_AddIn_Data" -Recurse -Force
   ```

3. **Reinstall**:
   - Copy the entire `src` folder to Fusion's add-ins directory
   - Restart Fusion 360

## Testing the Fix

After applying the import fix, test these scenarios:

### Test 1: Basic Load
```
1. Open Fusion 360
2. Go to Scripts and Add-Ins
3. Click "Run" on the add-in
4. Expected: Button appears in toolbar, no errors in log
```

### Test 2: Open Dialog
```
1. Click the "Push to GitHub" button
2. Expected: Dialog opens with all fields visible
3. Check log file for any warnings
```

### Test 3: Error Recovery
```
1. Try to proceed without configuring a repo
2. Expected: Helpful error message, not a crash
3. Dialog should stay open for corrections
```

## Log File Analysis

When reviewing logs, look for:

- ✅ `'Push to GitHub (ZAC)' Logger initialized` - Good start
- ✅ `'Push to GitHub (ZAC)' Add-In Loaded and running` - Loaded successfully
- ❌ `ImportError` - Missing module
- ❌ `AttributeError` - API object not available
- ❌ `SyntaxError` - Code has syntax problems
- ❌ Traceback - Unhandled exception

## Quick Reference: File Locations

```
Add-in source:
c:\Users\ZCohe\OneDrive\Documents\Python Scripts\Fusion_to_GitHub\FusionToGitHub\src\

Fusion's add-ins folder:
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\

Log file:
%USERPROFILE%\.PushToGitHub_AddIn_Data\PushToGitHub.log

Config file:
%USERPROFILE%\.fusion_git_repos.json
```

## Status Check Command

Run this in PowerShell to check everything:

```powershell
# Quick status check
Write-Host "=== FusionToGitHub Status ===" -ForegroundColor Cyan

# Check if files exist
$src = "c:\Users\ZCohe\OneDrive\Documents\Python Scripts\Fusion_to_GitHub\FusionToGitHub\src"
Write-Host "`nSource files:" -ForegroundColor Yellow
Get-ChildItem $src\*.py | ForEach-Object { Write-Host "  ✓ $($_.Name)" -ForegroundColor Green }

# Check log
$log = "$env:USERPROFILE\.PushToGitHub_AddIn_Data\PushToGitHub.log"
if (Test-Path $log) {
    Write-Host "`nLog file exists" -ForegroundColor Green
    Write-Host "Last modified: $((Get-Item $log).LastWriteTime)" -ForegroundColor Gray
} else {
    Write-Host "`nNo log file yet" -ForegroundColor Yellow
}

# Check for recent errors
if (Test-Path $log) {
    Write-Host "`nRecent log entries:" -ForegroundColor Yellow
    Get-Content $log -Tail 5 | ForEach-Object {
        if ($_ -match "ERROR|CRITICAL") {
            Write-Host "  ❌ $_" -ForegroundColor Red
        } elseif ($_ -match "WARNING") {
            Write-Host "  ⚠  $_" -ForegroundColor Yellow
        } else {
            Write-Host "  $_" -ForegroundColor Gray
        }
    }
}
```

## Success Indicators

You'll know it's working when:
1. ✅ Button appears in toolbar
2. ✅ Clicking button opens dialog
3. ✅ Log file shows "Add-In Loaded and running"
4. ✅ No error messages in log or Fusion's text commands

## Contact/Debug Info

If the issue persists after trying all troubleshooting steps:

1. Run `diagnostic.py` and save the output
2. Check the full log file
3. Look for Python errors in Fusion's Text Commands window
4. Try the add-in with a simple test design
