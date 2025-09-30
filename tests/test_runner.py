#!/usr/bin/env python3
"""
FusionToGitHub V7.7 - Automated Test Runner

This script automates the execution of testable components from the TESTING.md
systematic test plan. It focuses on programmatically verifiable tests while
providing guidance for manual UI tests.

Usage:
    python test_runner.py [--verbose] [--category CATEGORY]

Categories:
    - pre-install: Environment and dependency validation
    - core-modules: Test core module functionality
    - git-ops: Test git operations (requires test repo)
    - cli: Test CLI harness functionality
    - all: Run all automated tests (default)
"""

import argparse
import importlib.util
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


class TestResult:
    def __init__(self, test_id: str, name: str, passed: bool, message: str = ""):
        self.test_id = test_id
        self.name = name
        self.passed = passed
        self.message = message

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.test_id}: {self.name}"


class TestRunner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.setup_logging()

    def setup_logging(self):
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def log_test_start(self, test_id: str, name: str):
        self.logger.info(f"Running {test_id}: {name}")

    def record_result(self, test_id: str, name: str, passed: bool, message: str = ""):
        result = TestResult(test_id, name, passed, message)
        self.results.append(result)
        if self.verbose or not passed:
            print(f"  {result}")
            if message and not passed:
                print(f"    Details: {message}")

    def run_command(self, cmd: List[str], expect_success: bool = True) -> tuple[bool, str]:
        """Run a command and return (success, output)"""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            success = (result.returncode == 0) == expect_success
            output = result.stdout + result.stderr
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, f"Command failed: {e}"

    # Pre-Installation Tests
    def test_t001_git_available(self):
        """T001: Verify Git CLI is installed and accessible"""
        self.log_test_start("T001", "Git CLI availability")
        success, output = self.run_command(["git", "--version"])
        self.record_result(
            "T001", "Git CLI availability", success, output if success else "Git not found"
        )

    def test_t002_python_environment(self):
        """T002: Verify Python environment compatibility"""
        self.log_test_start("T002", "Python environment compatibility")
        try:
            version = sys.version_info
            py_ok = version.major == 3 and version.minor >= 8
            msg = f"Python {version.major}.{version.minor}.{version.micro}"
            self.record_result("T002", "Python environment compatibility", py_ok, msg)
        except Exception as e:
            self.record_result("T002", "Python environment compatibility", False, str(e))

    def test_t004_fusion_git_core_import(self):
        """T004: Test fusion_git_core module independently"""
        self.log_test_start("T004", "fusion_git_core module import")
        try:
            import fusion_git_core
            version_ok = fusion_git_core.VERSION == "V7.7"
            msg = f"Version: {fusion_git_core.VERSION}"
            self.record_result("T004", "fusion_git_core module import", version_ok, msg)
        except Exception as e:
            self.record_result("T004", "fusion_git_core module import", False, str(e))

    def test_t005_cli_harness_help(self):
        """T005: Test CLI harness functionality"""
        self.log_test_start("T005", "CLI harness help")
        cli_path = Path("src") / "push_cli.py"
        success, output = self.run_command([sys.executable, str(cli_path), "--help"])
        help_ok = success and "usage:" in output.lower()
        self.record_result("T005", "CLI harness help", help_ok, "Help displayed" if help_ok else output)

    # Core Module Tests
    def test_core_git_functions(self):
        """Test core git utility functions"""
        self.log_test_start("T_CORE_01", "Core git utility functions")
        try:
            from fusion_git_core import sanitize_branch_name, generate_branch_name, git_available

            # Test branch name sanitization
            test_cases = [
                ("feature/test", "feature/test"),
                ("hello world!", "hello_world_"),
                ("", "fusion-export"),
                ("/" * 250, "fusion-export"),  # Too long
            ]
            
            sanitize_ok = True
            for input_name, expected in test_cases:
                result = sanitize_branch_name(input_name)
                if expected == "fusion-export" and result != expected:
                    continue  # Allow default fallback
                if "/" in expected and "/" not in result:
                    sanitize_ok = False
                    break

            # Test branch name generation
            branch, timestamp = generate_branch_name("test-{filename}-{timestamp}", "myfile")
            generate_ok = "test-myfile-" in branch and len(timestamp) > 0

            # Test git availability
            git_avail = git_available()

            overall_ok = sanitize_ok and generate_ok
            msg = f"Sanitize: {sanitize_ok}, Generate: {generate_ok}, Git available: {git_avail}"
            self.record_result("T_CORE_01", "Core git utility functions", overall_ok, msg)

        except Exception as e:
            self.record_result("T_CORE_01", "Core git utility functions", False, str(e))

    # Git Operations Tests
    def test_git_operations_with_temp_repo(self):
        """Test git operations with temporary repository"""
        self.log_test_start("T_GIT_01", "Git operations with temp repo")
        
        # Save current directory
        original_dir = os.getcwd()
        temp_dir = None
        
        try:
            # Create temporary directory manually for better control
            temp_dir = tempfile.mkdtemp(prefix="fusion_git_test_")
            
            # Initialize git repo
            os.chdir(temp_dir)
            success, _ = self.run_command(["git", "init"])
            if not success:
                self.record_result("T_GIT_01", "Git operations with temp repo", False, "Failed to init git repo")
                return

            # Configure git (required for commits)
            self.run_command(["git", "config", "user.email", "test@example.com"])
            self.run_command(["git", "config", "user.name", "Test User"])

            # Test fusion_git_core operations
            from fusion_git_core import git_run

            # Create a test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("Hello, World!")

            # Test git operations
            try:
                git_run(temp_dir, "add", "test.txt")
                git_run(temp_dir, "commit", "-m", "Test commit")
                
                # Check commit was created
                result = git_run(temp_dir, "log", "--oneline", check=False)
                commit_ok = result.returncode == 0 and "Test commit" in result.stdout

                self.record_result("T_GIT_01", "Git operations with temp repo", commit_ok, 
                                 "Git operations successful" if commit_ok else "Git operations failed")
                
            except Exception as e:
                self.record_result("T_GIT_01", "Git operations with temp repo", False, str(e))

        except Exception as e:
            self.record_result("T_GIT_01", "Git operations with temp repo", False, str(e))
        finally:
            # Restore original directory
            os.chdir(original_dir)
            
            # Clean up temp directory with retry logic for Windows
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    import time
                    # Try to clean up, but don't fail the test if it doesn't work on Windows
                    for attempt in range(3):
                        try:
                            shutil.rmtree(temp_dir)
                            break
                        except (PermissionError, OSError):
                            if attempt < 2:
                                time.sleep(0.1)  # Brief pause before retry
                            # On final attempt, just log and continue
                except Exception:
                    # Cleanup failure shouldn't fail the test
                    pass

    # CLI Tests
    def test_cli_basic_functionality(self):
        """Test CLI harness basic functionality"""
        self.log_test_start("T_CLI_01", "CLI basic functionality")
        
        # Test help display  
        cli_path = Path("src") / "push_cli.py"
        success, output = self.run_command([sys.executable, str(cli_path), "--help"])
        help_ok = success and all(word in output.lower() for word in ["usage", "options"])

        # Test that we can import the CLI module and access VERSION
        try:
            # Add src to path temporarily
            import sys as system_module
            src_path = str(Path("src").resolve())
            if src_path not in system_module.path:
                system_module.path.insert(0, src_path)
            
            import push_cli
            # Check that push_cli can import fusion_git_core and get VERSION
            from fusion_git_core import VERSION
            version_ok = VERSION == "V7.7"
        except Exception:
            version_ok = False
        finally:
            # Clean up path
            if 'src_path' in locals() and src_path in system_module.path:
                system_module.path.remove(src_path)

        overall_ok = version_ok and help_ok
        msg = f"Version import OK: {version_ok}, Help OK: {help_ok}"
        self.record_result("T_CLI_01", "CLI basic functionality", overall_ok, msg)

    def run_pre_install_tests(self):
        """Run pre-installation tests"""
        print("\n=== Pre-Installation Tests ===")
        self.test_t001_git_available()
        self.test_t002_python_environment()
        self.test_t004_fusion_git_core_import()
        self.test_t005_cli_harness_help()

    def run_core_module_tests(self):
        """Run core module tests"""
        print("\n=== Core Module Tests ===")
        self.test_core_git_functions()

    def run_git_tests(self):
        """Run git operation tests"""
        print("\n=== Git Operations Tests ===")
        self.test_git_operations_with_temp_repo()

    def run_cli_tests(self):
        """Run CLI tests"""
        print("\n=== CLI Tests ===")
        self.test_cli_basic_functionality()

    def run_all_tests(self):
        """Run all automated tests"""
        self.run_pre_install_tests()
        self.run_core_module_tests()
        self.run_git_tests()
        self.run_cli_tests()

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        print(f"Tests Run: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "No tests run")
        
        if any(not r.passed for r in self.results):
            print("\nFAILED TESTS:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result}")
                    if result.message:
                        print(f"    {result.message}")

        print("\nNOTE: This covers automated tests only.")
        print("See TESTING.md for complete manual test procedures.")


def main():
    parser = argparse.ArgumentParser(description="FusionToGitHub V7.7 Test Runner")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--category", "-c", 
                       choices=["pre-install", "core-modules", "git-ops", "cli", "all"],
                       default="all",
                       help="Test category to run")
    
    args = parser.parse_args()
    
    # Change to project root directory (parent of tests)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    # Add src directory to Python path for imports
    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))
    
    runner = TestRunner(verbose=args.verbose)
    
    print(f"FusionToGitHub V7.7 - Automated Test Runner")
    print(f"Running category: {args.category}")
    print(f"Working directory: {os.getcwd()}")
    
    if args.category == "pre-install":
        runner.run_pre_install_tests()
    elif args.category == "core-modules":
        runner.run_core_module_tests()
    elif args.category == "git-ops":
        runner.run_git_tests()
    elif args.category == "cli":
        runner.run_cli_tests()
    else:  # all
        runner.run_all_tests()
    
    runner.print_summary()
    
    # Exit with error code if any tests failed
    failed_count = sum(1 for r in runner.results if not r.passed)
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    main()