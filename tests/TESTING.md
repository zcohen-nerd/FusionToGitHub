# FusionToGitHub V7.7 - Systematic Test Plan

## Overview

This document provides a comprehensive testing strategy for the FusionToGitHub V7.7 add-in to ensure all functionality works correctly across different scenarios and environments.

**Test Environment Requirements:**
- Autodesk Fusion 360 (latest version)
- Windows 10/11 with PowerShell
- Git CLI installed and accessible
- GitHub account with repository access
- GitHub authentication available (PAT for HTTPS, or SSH key workflow)

---

## Test Categories

### 1. Pre-Installation Tests

#### 1.1 Environment Validation
- [ ] **T001**: Verify Git CLI is installed and accessible
  - Command: `git --version`
  - Expected: Git version displayed
  - Failure: Install Git for Windows

- [ ] **T002**: Verify Python environment compatibility
  - Check: Python 3.8+ available
  - Check: Required modules can be imported
  - Expected: No import errors

- [ ] **T003**: Verify file system permissions
  - Check: Write access to Fusion 360 add-ins directory
  - Check: Write access to temp directories
  - Expected: No permission errors

#### 1.2 Core Module Tests
- [ ] **T004**: Test fusion_git_core module independently
  - Command: `python -c "import fusion_git_core; print(fusion_git_core.VERSION)"`
  - Expected: "V7.7" displayed
  - Validates: Core module loads correctly

- [ ] **T005**: Test CLI harness functionality
  - Command: `python push_cli.py --help`
  - Expected: Help text displayed with all options
  - Validates: CLI interface works

---

### 2. Installation & Setup Tests

#### 2.1 Add-in Installation
- [ ] **T006**: Install add-in in Fusion 360
  - Action: Copy files to Fusion add-ins directory
  - Action: Enable add-in in Fusion preferences
  - Expected: Add-in appears in Scripts and Add-Ins panel
  - Expected: No error messages in Fusion console

#### 2.2 First Launch Tests
- [ ] **T007**: First-time dialog launch
  - Action: Launch "Push to GitHub (ZAC)" from toolbar
  - Expected: Dialog opens with default values
  - Expected: No repository configurations loaded initially

- [ ] **T008**: Git availability check
  - Trigger: Dialog opens
  - Expected: Git status indicator shows "Available" or error message
  - Validates: Git detection works correctly

---

### 3. Repository Configuration Tests

#### 3.1 New Repository Setup
- [ ] **T009**: Add new GitHub repository
  - Action: Select "+ Add new GitHub repo..." option
  - Action: Fill in Repository Name, GitHub URL, and Local Folder
  - Expected: Fields become visible/hidden appropriately
  - Expected: Real-time validation shows status

- [ ] **T010**: Repository path validation
  - Test Cases:
    - Valid existing git repository
    - Non-existent directory
    - Directory without .git folder
    - Invalid path characters
  - Expected: Appropriate validation messages

- [ ] **T011**: GitHub URL validation
  - Test Cases:
    - Valid GitHub HTTPS URL
    - Valid GitHub SSH URL
    - Invalid URL format
    - Non-GitHub URL
  - Expected: Appropriate validation messages

- [ ] **T012**: Stored token (PAT) validation
  - Test Cases:
    - Valid PAT with repo permissions
    - Invalid/expired PAT
    - Empty PAT field
  - Expected: Token stored securely in Windows Credential Manager

#### 3.2 Repository Selection
- [ ] **T013**: Load existing repository configurations
  - Prerequisite: Have saved repository configs
  - Action: Open dialog
  - Expected: Repository dropdown populated with saved repos
  - Expected: Last-used repository pre-selected

- [ ] **T014**: Repository persistence
  - Action: Add new repository, close dialog, reopen
  - Expected: New repository appears in dropdown
  - Expected: Configuration persisted to `~/.fusion_git_repos.json`

---

### 4. Export Functionality Tests

#### 4.1 Design Export
- [ ] **T015**: Export active design (default format)
  - Prerequisite: Have active Fusion design
  - Action: Use default export settings
  - Expected: Design exported to repository subfolder
  - Expected: File appears in correct location

- [ ] **T016**: Export format selection
  - Test Cases:
    - Fusion Archive (.f3d)
    - STEP (.step/.stp)
    - IGES (.iges/.igs)
    - STL (.stl)
  - Expected: File exported in correct format

- [ ] **T017**: Export subfolder configuration
  - Test Cases:
    - Default subfolder (design name)
    - Custom subfolder name
    - Nested subfolder path
  - Expected: Files exported to correct directory structure

- [ ] **T018**: Export with existing files
  - Setup: Export same design twice
  - Expected: Behavior based on overwrite settings
  - Expected: No data loss or corruption

#### 4.2 Changelog Generation
- [ ] **T019**: Automatic changelog creation
  - Action: Export design with changelog enabled
  - Expected: CHANGELOG.md created/updated in repository
  - Expected: Entry includes timestamp and design information

- [ ] **T020**: Custom changelog messages
  - Action: Provide custom commit message
  - Expected: Custom message appears in changelog
  - Expected: Standard format maintained

---

### 5. Git Operations Tests

#### 5.1 Branch Management
- [ ] **T021**: Branch name generation
  - Test Cases:
    - Default template: `fusion-export/{filename}-{timestamp}`
    - Custom template with placeholders
    - Special characters in design name
  - Expected: Valid git branch names generated

- [ ] **T022**: Branch creation and switching
  - Action: Execute git operations with new branch
  - Expected: New branch created from current HEAD
  - Expected: Working directory switched to new branch

- [ ] **T023**: Branch override functionality
  - Action: Set a custom value in "Branch Name Override"
  - Expected: Override branch name is used for the push
  - Expected: Unsupported characters are sanitized safely

#### 5.2 Commit Operations
- [ ] **T024**: File staging and commit
  - Action: Complete export and git workflow
  - Expected: Exported files staged for commit
  - Expected: Commit created with appropriate message

- [ ] **T025**: Commit message customization
  - Test Cases:
    - Default generated message
    - Custom user message
    - Message with special characters
  - Expected: Messages preserved correctly in git history

#### 5.3 Push Operations
- [ ] **T026**: Push to GitHub with PAT authentication
  - Action: Complete full workflow including push
  - Expected: Changes pushed to GitHub repository
  - Expected: No authentication errors

- [ ] **T027**: Push failure handling
  - Test Cases:
    - Network connectivity issues
    - Invalid credentials
    - Repository access denied
  - Expected: Appropriate error messages
  - Expected: Local changes preserved

---

### 6. UI/UX Tests

#### 6.1 Dialog Behavior
- [ ] **T028**: Field validation feedback
  - Action: Enter invalid data in various fields
  - Expected: Real-time validation indicators
  - Expected: Clear error messages

- [ ] **T029**: Progress indication
  - Action: Execute long-running operations
  - Expected: Progress bar or status updates
  - Expected: UI remains responsive

- [ ] **T030**: Settings persistence
  - Action: Change settings, close/reopen dialog
  - Expected: Settings remembered between sessions
  - Expected: User preferences maintained

#### 6.2 Error Handling
- [ ] **T031**: Git not available
  - Setup: Temporarily make git inaccessible
  - Expected: Clear error message with resolution steps
  - Expected: Dialog functionality gracefully degraded

- [ ] **T032**: Repository access errors
  - Test Cases:
    - Repository doesn't exist
    - No write permissions
    - Network issues
  - Expected: Specific error messages
  - Expected: Suggested corrective actions

#### 6.3 Logging and Diagnostics
- [ ] **T033**: Log file creation and rotation
  - Action: Execute multiple operations
  - Expected: Log files created in appropriate location
  - Expected: Log rotation works (size/age limits)

- [ ] **T034**: Log level controls
  - Action: Change log level settings
  - Expected: Log verbosity changes appropriately
  - Expected: Debug information available when needed

- [ ] **T035**: Open log file functionality
  - Action: In Logging, click "Open Log File…"
  - Expected: Log file opens in default editor
  - Expected: Recent entries visible

---

### 7. Integration Tests

#### 7.1 End-to-End Workflows
- [ ] **T036**: Complete new repository workflow
  - Steps:
    1. Create new GitHub repository
    2. Configure in add-in
    3. Export design
    4. Commit and push
  - Expected: Repository created and populated on GitHub

- [ ] **T037**: Complete existing repository workflow
  - Steps:
    1. Select existing repository
    2. Export design with custom settings
    3. Review and commit changes
    4. Push to GitHub
  - Expected: Changes appear in GitHub repository

- [ ] **T038**: Multiple design exports
  - Steps:
    1. Export multiple designs to same repository
    2. Use different export formats
    3. Verify branch/commit history
  - Expected: Clean git history with all exports

#### 7.2 Cross-Platform Compatibility
- [ ] **T039**: Windows path handling
  - Test Cases:
    - Paths with spaces
    - Paths with special characters
    - Long path names
    - Network drive paths
  - Expected: Paths handled correctly

- [ ] **T040**: Git credential integration
  - Action: Test with Windows Credential Manager
  - Expected: PAT stored and retrieved securely
  - Expected: No credentials in plain text

---

### 8. Performance Tests

#### 8.1 Large File Handling
- [ ] **T041**: Large design export
  - Setup: Complex design with many components
  - Expected: Export completes without timeout
  - Expected: Memory usage remains reasonable

- [ ] **T042**: Repository with many files
  - Setup: Repository with large number of existing files
  - Expected: Git operations complete in reasonable time
  - Expected: No performance degradation

#### 8.2 Network Performance
- [ ] **T043**: Slow network conditions
  - Setup: Simulate slow network connection
  - Expected: Operations complete with appropriate timeouts
  - Expected: User informed of network delays

---

### 9. Security Tests

#### 9.1 Credential Security
- [ ] **T044**: PAT storage security
  - Action: Store PAT, check system credential store
  - Expected: PAT encrypted in Windows Credential Manager
  - Expected: No PAT visible in log files or temp files

- [ ] **T045**: Temporary file cleanup
  - Action: Complete export workflow
  - Expected: Temporary files cleaned up
  - Expected: No sensitive data left in temp directories

#### 9.2 Input Validation
- [ ] **T046**: Malicious input handling
  - Test Cases:
    - Command injection in paths
    - Script injection in messages
    - Path traversal attempts
  - Expected: Inputs sanitized appropriately
  - Expected: No system compromise

---

### 10. Recovery Tests

#### 10.1 Interruption Handling
- [ ] **T047**: Process interruption
  - Action: Interrupt export/git operations mid-process
  - Expected: Graceful handling of interruption
  - Expected: Repository left in consistent state

- [ ] **T048**: Fusion crash recovery
  - Setup: Simulate Fusion crash during operation
  - Expected: No repository corruption
  - Expected: Operations can be resumed

#### 10.2 Data Recovery
- [ ] **T049**: Failed operation recovery
  - Action: Recover from failed git push
  - Expected: Local changes preserved
  - Expected: User can retry operation

---

## Test Execution Guidelines

### Before Testing
1. **Environment Setup**:
   - Clean Fusion 360 installation
   - Fresh git repository for testing
   - Valid GitHub account and PAT
   - Backup any important data

2. **Test Data Preparation**:
   - Simple test designs for basic functionality
   - Complex designs for performance testing
   - Various file formats for export testing

### During Testing
1. **Documentation**:
   - Record test results for each test case
   - Document any deviations from expected behavior
   - Capture screenshots for UI tests
   - Save log files for analysis

2. **Issue Tracking**:
   - Note exact steps to reproduce issues
   - Record system configuration details
   - Classify issues by severity and impact

### After Testing
1. **Results Analysis**:
   - Categorize passed/failed/blocked tests
   - Identify patterns in failures
   - Assess overall system stability

2. **Reporting**:
   - Generate comprehensive test report
   - Include recommendations for fixes
   - Prioritize issues for resolution

---

## Test Result Template

For each test, record:

```
Test ID: T###
Test Name: [Descriptive name]
Date: [YYYY-MM-DD]
Tester: [Name]
Environment: [Fusion version, OS, Git version]

Steps Executed:
1. [Step 1]
2. [Step 2]
...

Expected Result:
[What should happen]

Actual Result:
[What actually happened]

Status: [PASS/FAIL/BLOCKED]
Notes: [Additional observations]
```

---

## Success Criteria

The FusionToGitHub V7.7 add-in is considered fully functional when:

- **Core Functionality**: All T001-T035 tests pass
- **Integration**: All T036-T040 tests pass  
- **Performance**: T041-T043 meet acceptable thresholds
- **Security**: T044-T046 demonstrate secure operation
- **Recovery**: T047-T049 show graceful error handling

**Acceptance Threshold**: 95% of tests must pass, with no critical severity failures in core functionality areas.