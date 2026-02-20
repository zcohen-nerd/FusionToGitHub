# FusionToGitHub V7.7 - Manual Test Checklist

## Quick Manual Test Checklist for Fusion 360

This checklist provides a streamlined set of manual tests to verify core functionality within Fusion 360. Use this for quick validation after installation or updates.

### Pre-Test Setup
- [ ] Fusion 360 is running with a design loaded
- [ ] Git is installed and accessible from command line
- [ ] Valid GitHub repository available (PAT required for HTTPS)
- [ ] Add-in installed and enabled in Fusion 360

---

### 🔧 Basic Functionality Tests (10 minutes)

#### Test 1: Add-in Launch
- [ ] **Step**: Click "Push to GitHub (ZAC)" button in toolbar
- [ ] **Expected**: Dialog opens without errors
- [ ] **Expected**: Git status shows "Available"
- [ ] **If fails**: Check git installation and PATH

#### Test 2: Repository Configuration
- [ ] **Step**: Select "+ Add new GitHub repo..." 
- [ ] **Step**: Enter Repository Name: `test-repo` (or leave blank to auto-fill)
- [ ] **Step**: Enter GitHub URL: `https://github.com/YOUR_USERNAME/test-repo`
- [ ] **Step**: Set local folder: `C:\temp\test-fusion-repo`
- [ ] **Step**: Optional (Windows): Advanced → "Use Stored Token" → "Manage Token…" and enter PAT
- [ ] **Expected**: Fields validate in real-time
- [ ] **Expected**: No red error indicators

#### Test 3: Simple Export and Push
- [ ] **Step**: Keep default export settings
- [ ] **Step**: Set commit message: "Test export from Fusion"
- [ ] **Step**: Click "OK"
- [ ] **Expected**: Progress dialog appears
- [ ] **Expected**: Success message after completion
- [ ] **Expected**: Files appear in GitHub repository

---

### 🔍 Advanced Functionality Tests (15 minutes)

#### Test 4: Custom Export Settings
- [ ] **Step**: Change export format to STEP
- [ ] **Step**: Set custom subfolder: "fusion-exports/step-files"
- [ ] **Step**: Set Branch Name Override: `feature/manual-test-override`
- [ ] **Expected**: Branch override value is used for the push
- [ ] **Expected**: Branch name is sanitized if invalid characters are entered

#### Test 5: Branch Template
- [ ] **Step**: Set branch template: `feature/{filename}-{timestamp}`
- [ ] **Step**: Export with current design name "TestDesign"
- [ ] **Expected**: Branch name like "feature/TestDesign-20250930-143022"
- [ ] **Expected**: Branch created and switched to

#### Test 6: Changelog Generation
- [ ] **Step**: Enable changelog option
- [ ] **Step**: Export with message "Added TestDesign v2"
- [ ] **Expected**: CHANGELOG.md created/updated in repository
- [ ] **Expected**: Entry contains timestamp and message

---

### 🚨 Error Handling Tests (10 minutes)

#### Test 7: Invalid Repository
- [ ] **Step**: Try to use non-existent local path
- [ ] **Expected**: Clear error message about path not existing
- [ ] **Expected**: Dialog remains open for correction

#### Test 8: Network Issues
- [ ] **Step**: Temporarily disconnect from internet
- [ ] **Step**: Try to push to GitHub
- [ ] **Expected**: Meaningful error about network connectivity
- [ ] **Expected**: Local changes preserved

#### Test 9: Invalid PAT
- [ ] **Step**: Use expired or invalid PAT
- [ ] **Step**: Try to push to GitHub  
- [ ] **Expected**: Authentication error with clear message
- [ ] **Expected**: Suggestion to check PAT permissions

---

### 🔒 Security Validation (5 minutes)

#### Test 10: PAT Storage
- [ ] **Step**: Enter PAT and save repository configuration
- [ ] **Step**: Check Windows Credential Manager
- [ ] **Expected**: PAT stored securely under "git:https://github.com"
- [ ] **Expected**: No PAT visible in log files

#### Test 11: Temporary File Cleanup
- [ ] **Step**: Complete an export operation
- [ ] **Step**: Check system temp directory
- [ ] **Expected**: No leftover Fusion export files
- [ ] **Expected**: No sensitive data in temp files

---

### 📊 Performance Validation (10 minutes)

#### Test 12: Large Design Export
- [ ] **Step**: Open complex design with many components
- [ ] **Step**: Export in native Fusion format
- [ ] **Expected**: Export completes within reasonable time (<2 minutes)
- [ ] **Expected**: No memory errors or crashes

#### Test 13: Repository with History
- [ ] **Step**: Use repository with existing commit history
- [ ] **Step**: Export additional design
- [ ] **Expected**: Git operations complete normally
- [ ] **Expected**: New commits added to existing history

---

### 🔄 Integration Tests (15 minutes)

#### Test 14: Multiple Export Formats
- [ ] **Step**: Export same design in 3 different formats (F3D, STEP, STL)
- [ ] **Step**: Use different subfolders for each
- [ ] **Expected**: All formats exported correctly
- [ ] **Expected**: Clean repository structure maintained

#### Test 15: Workflow Interruption Recovery
- [ ] **Step**: Start export operation
- [ ] **Step**: Close Fusion 360 mid-operation (simulate crash)
- [ ] **Step**: Restart Fusion and check repository state
- [ ] **Expected**: Repository not corrupted
- [ ] **Expected**: Can resume operations normally

#### Test 16: Settings Persistence
- [ ] **Step**: Configure custom settings (branch template, export format, etc.)
- [ ] **Step**: Close and reopen Fusion 360
- [ ] **Step**: Open add-in dialog
- [ ] **Expected**: All custom settings remembered
- [ ] **Expected**: Last-used repository pre-selected

---

## Test Results Template

**Date**: ___________  
**Tester**: ___________  
**Fusion Version**: ___________  
**Add-in Version**: V7.7  

### Basic Functionality (Pass/Fail)
- [ ] Test 1: Add-in Launch
- [ ] Test 2: Repository Configuration  
- [ ] Test 3: Simple Export and Push

### Advanced Functionality (Pass/Fail)
- [ ] Test 4: Custom Export Settings
- [ ] Test 5: Branch Template
- [ ] Test 6: Changelog Generation

### Error Handling (Pass/Fail)
- [ ] Test 7: Invalid Repository
- [ ] Test 8: Network Issues
- [ ] Test 9: Invalid PAT

### Security Validation (Pass/Fail)
- [ ] Test 10: PAT Storage
- [ ] Test 11: Temporary File Cleanup

### Performance Validation (Pass/Fail)
- [ ] Test 12: Large Design Export
- [ ] Test 13: Repository with History

### Integration Tests (Pass/Fail)
- [ ] Test 14: Multiple Export Formats
- [ ] Test 15: Workflow Interruption Recovery
- [ ] Test 16: Settings Persistence

**Overall Result**: _____ / 16 tests passed

**Critical Issues Found**:
_________________________________
_________________________________

**Recommendations**:
_________________________________
_________________________________

---

## Quick Smoke Test (3 minutes)

For rapid validation, run this minimal test:

1. **Launch**: Open add-in dialog ✓
2. **Configure**: Add a test repository ✓  
3. **Export**: Push current design with default settings ✓
4. **Verify**: Check GitHub repository for new files ✓

If all 4 steps pass, basic functionality is working.