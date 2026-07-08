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
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional


class _PipelineTestUI:
    """GitUI double that records messages and auto-accepts confirmations."""

    def __init__(self, confirm_answer: bool = True):
        self.infos: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self._confirm_answer = confirm_answer

    def info(self, message: str) -> None:
        self.infos.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, message: str) -> bool:
        return self._confirm_answer


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

            # Test branch name sanitization with exact expectations
            test_cases = [
                ("feature/test", "feature/test"),
                ("hello world!", "hello_world_"),
                ("", "fusion-export"),
                ("/" * 250, "fusion-export"),  # collapses to nothing -> fallback
                ("a" * 250, "a" * 200),  # length cap
                ("  spaced  ", "spaced"),
                ("trailing.dots..", "trailing.dots"),
            ]

            sanitize_failures = []
            for input_name, expected in test_cases:
                result = sanitize_branch_name(input_name)
                if result != expected:
                    sanitize_failures.append(
                        f"{input_name[:30]!r} -> {result!r} (expected {expected!r})"
                    )
            sanitize_ok = not sanitize_failures

            # Test branch name generation
            branch, timestamp = generate_branch_name("test-{filename}-{timestamp}", "myfile")
            generate_ok = branch.startswith("test-myfile-") and branch.endswith(timestamp)

            # Test git availability
            git_avail = git_available()

            overall_ok = sanitize_ok and generate_ok
            msg = f"Sanitize: {sanitize_ok}, Generate: {generate_ok}, Git available: {git_avail}"
            if sanitize_failures:
                msg += "; " + "; ".join(sanitize_failures)
            self.record_result("T_CORE_01", "Core git utility functions", overall_ok, msg)

        except Exception as e:
            self.record_result("T_CORE_01", "Core git utility functions", False, str(e))

    def test_dialog_helpers_url_functions(self):
        """T_CORE_02: GitHub URL conversion and repo name derivation"""
        self.log_test_start("T_CORE_02", "URL conversion helpers")
        try:
            from dialog_helpers import convert_github_url, derive_repo_name_from_url

            convert_cases = [
                ("https://github.com/user/repo", "https://github.com/user/repo.git"),
                ("https://github.com/user/repo/", "https://github.com/user/repo.git"),
                ("https://github.com/user/repo?tab=readme", "https://github.com/user/repo.git"),
                ("https://github.com/user/repo/tree/main", "https://github.com/user/repo.git"),
                ("https://github.com/user/repo/blob/main/f.py", "https://github.com/user/repo.git"),
                ("https://www.github.com/user/repo", "https://github.com/user/repo.git"),
                ("github.com/user/repo", "https://github.com/user/repo.git"),
                ("https://github.com/user/repo.git", "https://github.com/user/repo.git"),
                ("git@github.com:user/repo.git", "git@github.com:user/repo.git"),
                ("https://gitlab.com/user/repo", "https://gitlab.com/user/repo"),
                # Partially typed values must never be mangled
                ("my-repo", "my-repo"),
                ("m", "m"),
                ("https://github.com/user", "https://github.com/user"),
                ("", ""),
            ]
            failures = []
            for raw, expected in convert_cases:
                result = convert_github_url(raw)
                if result != expected:
                    failures.append(f"convert {raw!r} -> {result!r} (expected {expected!r})")

            derive_cases = [
                ("https://github.com/user/repo.git", "repo"),
                ("https://github.com/user/repo", "repo"),
                ("git@github.com:user/repo.git", "repo"),
                ("git@github.com:repo.git", "repo"),
                ("", ""),
            ]
            for raw, expected in derive_cases:
                result = derive_repo_name_from_url(raw)
                if result != expected:
                    failures.append(f"derive {raw!r} -> {result!r} (expected {expected!r})")

            self.record_result(
                "T_CORE_02", "URL conversion helpers", not failures, "; ".join(failures)
            )
        except Exception as e:
            self.record_result("T_CORE_02", "URL conversion helpers", False, str(e))

    def test_askpass_script_security(self):
        """T_CORE_03: askpass script contains no secrets and echoes credentials"""
        self.log_test_start("T_CORE_03", "Askpass script security")
        try:
            from fusion_git_core import IS_WINDOWS, git_askpass_env

            username = "user@example.com"
            token = "ghp_SecretToken123&x%y"
            ok = True
            details = []
            with git_askpass_env(username, token) as env_map:
                script_path = env_map["GIT_ASKPASS"]
                with open(script_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                if token in content or username in content:
                    ok = False
                    details.append("credentials were written into the askpass script")

                run_env = {**os.environ, **env_map}
                if IS_WINDOWS:
                    base_cmd = ["cmd", "/d", "/c", script_path]
                else:
                    base_cmd = ["/bin/sh", script_path]
                out_user = subprocess.run(
                    base_cmd + ["Username for 'https://github.com':"],
                    capture_output=True, text=True, env=run_env,
                ).stdout.strip()
                out_token = subprocess.run(
                    base_cmd + ["Password for 'https://github.com':"],
                    capture_output=True, text=True, env=run_env,
                ).stdout.strip()
                # A password prompt whose URL contains the word "username"
                # must still yield the token (anchored prompt matching).
                out_tricky = subprocess.run(
                    base_cmd + ["Password for 'https://myusername@github.com':"],
                    capture_output=True, text=True, env=run_env,
                ).stdout.strip()
                if out_user != username:
                    ok = False
                    details.append(f"username echo wrong: {out_user!r}")
                if out_token != token:
                    ok = False
                    details.append(f"token echo wrong: {out_token!r}")
                if out_tricky != token:
                    ok = False
                    details.append(f"username-in-URL password prompt returned {out_tricky!r}")

            if os.path.exists(script_path):
                ok = False
                details.append("askpass script not cleaned up after use")

            self.record_result("T_CORE_03", "Askpass script security", ok, "; ".join(details))
        except Exception as e:
            self.record_result("T_CORE_03", "Askpass script security", False, str(e))

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
        inserted_src_path = False
        try:
            # Add src to path temporarily
            import sys as system_module
            src_path = str(Path("src").resolve())
            if src_path not in system_module.path:
                system_module.path.insert(0, src_path)
                inserted_src_path = True

            import push_cli  # noqa: F401
            # Check that push_cli can import fusion_git_core and get VERSION
            from fusion_git_core import VERSION
            version_ok = VERSION == "V7.7"
        except Exception:
            version_ok = False
        finally:
            # Only remove the path entry this test added itself
            if inserted_src_path and src_path in system_module.path:
                system_module.path.remove(src_path)

        overall_ok = version_ok and help_ok
        msg = f"Version import OK: {version_ok}, Help OK: {help_ok}"
        self.record_result("T_CLI_01", "CLI basic functionality", overall_ok, msg)

    # Pipeline Integration Tests
    #
    # These exercise handle_git_operations end-to-end against local bare
    # repositories, covering the scenarios that previously failed silently:
    # first export, re-export of a changed file, pull-rebase conflicts, and
    # brand-new repositories.

    @staticmethod
    def _cleanup_dir(path: Optional[str]):
        if not path or not os.path.exists(path):
            return
        for attempt in range(3):
            try:
                shutil.rmtree(path)
                return
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.1)

    @staticmethod
    def _make_seeded_remote(base_dir: str):
        """Create a bare origin plus a work clone with one pushed commit.

        Returns (origin_path, work_path, branch_name).
        """
        from fusion_git_core import git_run

        origin = os.path.join(base_dir, "origin.git")
        work = os.path.join(base_dir, "work")
        git_run(base_dir, "init", "--bare", origin)
        git_run(base_dir, "init", work)
        branch = git_run(work, "symbolic-ref", "--short", "HEAD").stdout.strip()
        with open(os.path.join(work, "readme.md"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        git_run(work, "add", ".")
        git_run(work, "commit", "-m", "seed commit")
        git_run(work, "remote", "add", "origin", origin)
        git_run(work, "push", "-u", "origin", branch)
        return origin, work, branch

    @staticmethod
    def _write_file_materializer(dest_path: str, content: str):
        def materialize():
            with open(dest_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return [dest_path]

        return materialize

    def test_pipeline_first_export(self):
        """T_PIPE_01: first export of a new file must be committed and pushed."""
        self.log_test_start("T_PIPE_01", "Pipeline: first export of a new file")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe1_")
        try:
            from fusion_git_core import git_run, handle_git_operations

            origin, work, branch = self._make_seeded_remote(base_dir)
            export_path = os.path.join(work, "model.step")
            ui = _PipelineTestUI()

            result = handle_git_operations(
                work,
                [],
                "Design update: {filename}",
                "fusion-export/{filename}-{timestamp}",
                ui,
                "TestDesign",
                materialize_files=self._write_file_materializer(export_path, "EXPORT v1"),
            )

            ok = bool(result)
            details = []
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
            else:
                pushed = git_run(origin, "show", f"{result['branch']}:model.step", check=False)
                if pushed.returncode != 0 or pushed.stdout.strip() != "EXPORT v1":
                    ok = False
                    details.append(f"pushed content wrong: {pushed.stdout!r} / {pushed.stderr}")
                current = git_run(work, "symbolic-ref", "--short", "HEAD").stdout.strip()
                if current != branch:
                    ok = False
                    details.append(f"not restored to '{branch}' (on '{current}')")
                if os.path.exists(export_path) or os.path.exists(os.path.join(work, "CHANGELOG.md")):
                    ok = False
                    details.append("working tree not clean after restore")
            self.record_result(
                "T_PIPE_01", "Pipeline: first export of a new file", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_01", "Pipeline: first export of a new file", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_reexport_changed_file(self):
        """T_PIPE_02: re-export of a changed tracked file must push the NEW content."""
        self.log_test_start("T_PIPE_02", "Pipeline: re-export pushes new content")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe2_")
        try:
            from fusion_git_core import git_run, handle_git_operations

            origin, work, branch = self._make_seeded_remote(base_dir)
            export_path = os.path.join(work, "model.step")
            with open(export_path, "w", encoding="utf-8") as fh:
                fh.write("EXPORT v1")
            git_run(work, "add", "model.step")
            git_run(work, "commit", "-m", "first export")
            git_run(work, "push", "origin", branch)

            ui = _PipelineTestUI()
            result = handle_git_operations(
                work,
                [],
                "Design update: {filename}",
                "fusion-export/{filename}-{timestamp}",
                ui,
                "TestDesign",
                materialize_files=self._write_file_materializer(export_path, "EXPORT v2 CHANGED"),
            )

            ok = bool(result)
            details = []
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
            else:
                pushed = git_run(origin, "show", f"{result['branch']}:model.step", check=False)
                if pushed.returncode != 0 or pushed.stdout.strip() != "EXPORT v2 CHANGED":
                    ok = False
                    details.append(
                        f"stale content pushed (regression!): {pushed.stdout!r} / {pushed.stderr}"
                    )
                stash = git_run(work, "stash", "list").stdout.strip()
                if stash:
                    ok = False
                    details.append(f"stash not empty: {stash}")
            self.record_result(
                "T_PIPE_02", "Pipeline: re-export pushes new content", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_02", "Pipeline: re-export pushes new content", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_conflict_recovery(self):
        """T_PIPE_03: a pull-rebase conflict must not leave the repo mid-rebase."""
        self.log_test_start("T_PIPE_03", "Pipeline: conflict recovery")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe3_")
        try:
            from fusion_git_core import git_run, handle_git_operations

            origin, work, branch = self._make_seeded_remote(base_dir)

            # Diverge: remote gets one edit, local gets a conflicting one.
            other = os.path.join(base_dir, "other")
            git_run(base_dir, "clone", origin, other)
            with open(os.path.join(other, "readme.md"), "w", encoding="utf-8") as fh:
                fh.write("remote edit\n")
            git_run(other, "commit", "-am", "remote edit")
            git_run(other, "push", "origin", branch)

            with open(os.path.join(work, "readme.md"), "w", encoding="utf-8") as fh:
                fh.write("local edit\n")
            git_run(work, "commit", "-am", "local edit")

            # Plus an uncommitted file, so the auto-stash path runs too.
            scrap_path = os.path.join(work, "scrap.txt")
            with open(scrap_path, "w", encoding="utf-8") as fh:
                fh.write("precious uncommitted data")

            export_path = os.path.join(work, "model.step")
            ui = _PipelineTestUI(confirm_answer=True)  # accept stash + force push
            result = handle_git_operations(
                work,
                [],
                "Design update: {filename}",
                "fusion-export/{filename}-{timestamp}",
                ui,
                "TestDesign",
                materialize_files=self._write_file_materializer(export_path, "EXPORT vX"),
            )

            ok = bool(result)
            details = []
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
            else:
                if not result.get("force_push"):
                    ok = False
                    details.append("expected force push after conflict")
                for rebase_dir in ("rebase-merge", "rebase-apply"):
                    if os.path.exists(os.path.join(work, ".git", rebase_dir)):
                        ok = False
                        details.append(f"repo left mid-rebase ({rebase_dir})")
                current = git_run(work, "symbolic-ref", "--short", "HEAD").stdout.strip()
                if current != branch:
                    ok = False
                    details.append(f"not restored to '{branch}' (on '{current}')")
                stash = git_run(work, "stash", "list").stdout.strip()
                if stash:
                    ok = False
                    details.append(f"stash stranded: {stash}")
                if not os.path.exists(scrap_path):
                    ok = False
                    details.append("uncommitted file not restored")
                pushed = git_run(origin, "show", f"{result['branch']}:model.step", check=False)
                if pushed.returncode != 0 or pushed.stdout.strip() != "EXPORT vX":
                    ok = False
                    details.append(f"pushed content wrong: {pushed.stdout!r}")
            self.record_result(
                "T_PIPE_03", "Pipeline: conflict recovery", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_03", "Pipeline: conflict recovery", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_new_repo_bootstrap(self):
        """T_PIPE_04: setup_new_repository + first push against an empty remote."""
        self.log_test_start("T_PIPE_04", "Pipeline: new repository bootstrap")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe4_")
        try:
            from dialog_helpers import setup_new_repository
            from fusion_git_core import git_run, handle_git_operations

            origin = os.path.join(base_dir, "origin.git")
            git_run(base_dir, "init", "--bare", origin)
            local_path = os.path.join(base_dir, "MyNewRepo")

            error = setup_new_repository("MyNewRepo", local_path, origin, git_run)
            if error:
                self.record_result(
                    "T_PIPE_04", "Pipeline: new repository bootstrap", False, error
                )
                return

            export_path = os.path.join(local_path, "model.step")
            ui = _PipelineTestUI()
            result = handle_git_operations(
                local_path,
                [],
                "Design update: {filename}",
                "fusion-export/{filename}-{timestamp}",
                ui,
                "TestDesign",
                materialize_files=self._write_file_materializer(export_path, "FIRST EXPORT"),
            )

            ok = bool(result)
            details = []
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
            else:
                pushed = git_run(origin, "show", f"{result['branch']}:model.step", check=False)
                if pushed.returncode != 0 or pushed.stdout.strip() != "FIRST EXPORT":
                    ok = False
                    details.append(f"pushed content wrong: {pushed.stdout!r} / {pushed.stderr}")
            self.record_result(
                "T_PIPE_04", "Pipeline: new repository bootstrap", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_04", "Pipeline: new repository bootstrap", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_cli_end_to_end(self):
        """T_PIPE_05: push_cli commits an untracked file's current content."""
        self.log_test_start("T_PIPE_05", "Pipeline: CLI end-to-end")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe5_")
        try:
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            with open(os.path.join(work, "model.step"), "w", encoding="utf-8") as fh:
                fh.write("CLI EXPORT")

            cli_path = Path("src") / "push_cli.py"
            success, output = self.run_command(
                [
                    sys.executable,
                    str(cli_path),
                    "--repo",
                    work,
                    "--files",
                    "model.step",
                    "--design-name",
                    "CliDesign",
                    "--assume-yes",
                ]
            )
            ok = success
            details = []
            if not success:
                details.append(output)
            else:
                branches = git_run(origin, "branch", "--format", "%(refname:short)").stdout
                export_branch = next(
                    (b.strip() for b in branches.splitlines() if "fusion-export" in b), None
                )
                if not export_branch:
                    ok = False
                    details.append(f"no export branch on origin: {branches}")
                else:
                    pushed = git_run(origin, "show", f"{export_branch}:model.step", check=False)
                    if pushed.returncode != 0 or pushed.stdout.strip() != "CLI EXPORT":
                        ok = False
                        details.append(f"pushed content wrong: {pushed.stdout!r}")
                if not os.path.exists(os.path.join(work, "model.step")):
                    ok = False
                    details.append("local file not restored after run")
            self.record_result(
                "T_PIPE_05", "Pipeline: CLI end-to-end", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_05", "Pipeline: CLI end-to-end", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_branch_override_reuse(self):
        """T_PIPE_06: pushing twice to the same override branch appends a commit."""
        self.log_test_start("T_PIPE_06", "Pipeline: branch override reuse")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe6_")
        try:
            from fusion_git_core import git_run, handle_git_operations

            origin, work, branch = self._make_seeded_remote(base_dir)
            export_path = os.path.join(work, "model.step")

            def run_push(content, confirm_answer=True):
                ui = _PipelineTestUI(confirm_answer=confirm_answer)
                result = handle_git_operations(
                    work,
                    [],
                    "Design update: {filename}",
                    "fusion-export/{filename}-{timestamp}",
                    ui,
                    "TestDesign",
                    branch_override="my-export",
                    materialize_files=self._write_file_materializer(export_path, content),
                )
                return result, ui

            ok = True
            details = []

            result1, ui1 = run_push("EXPORT v1")
            if not result1 or result1.get("reused_branch"):
                ok = False
                details.append(f"first push wrong: {result1} {ui1.errors}")

            result2, ui2 = run_push("EXPORT v2")
            if not result2:
                ok = False
                details.append(f"second push failed (collision regression): {ui2.errors}")
            else:
                if not result2.get("reused_branch"):
                    ok = False
                    details.append("second push did not report branch reuse")
                pushed = git_run(origin, "show", "my-export:model.step", check=False)
                if pushed.returncode != 0 or pushed.stdout.strip() != "EXPORT v2":
                    ok = False
                    details.append(f"pushed content wrong: {pushed.stdout!r}")
                commit_count = git_run(origin, "rev-list", "--count", "my-export", check=False).stdout.strip()
                if commit_count != "3":  # seed + 2 exports
                    ok = False
                    details.append(f"expected 3 commits on my-export, got {commit_count}")

            # Declining the reuse prompt must cancel cleanly (and be
            # reported as a cancellation, not a failure).
            result3, ui3 = run_push("EXPORT v3", confirm_answer=False)
            if not (result3 and result3.get("cancelled")):
                ok = False
                details.append(f"declined reuse should report cancelled, got {result3!r}")
            if ui3.errors:
                ok = False
                details.append(f"decline should not raise errors: {ui3.errors}")
            current = git_run(work, "symbolic-ref", "--short", "HEAD").stdout.strip()
            if current != branch:
                ok = False
                details.append(f"not restored to '{branch}' after decline (on '{current}')")

            self.record_result(
                "T_PIPE_06", "Pipeline: branch override reuse", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_06", "Pipeline: branch override reuse", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_template_branch_uniquify(self):
        """T_PIPE_07: colliding template-generated branch names get uniquified."""
        self.log_test_start("T_PIPE_07", "Pipeline: template branch uniquify")
        base_dir = tempfile.mkdtemp(prefix="fusion_pipe7_")
        try:
            from fusion_git_core import git_run, handle_git_operations

            origin, work, branch = self._make_seeded_remote(base_dir)
            export_path = os.path.join(work, "model.step")

            def run_push(content):
                ui = _PipelineTestUI()
                # Timestamp-free template so both runs generate the same name.
                result = handle_git_operations(
                    work,
                    [],
                    "Design update: {filename}",
                    "fusion-export/{filename}",
                    ui,
                    "TestDesign",
                    materialize_files=self._write_file_materializer(export_path, content),
                )
                return result, ui

            ok = True
            details = []

            result1, ui1 = run_push("EXPORT v1")
            if not result1 or result1.get("branch") != "fusion-export/TestDesign":
                ok = False
                details.append(f"first push wrong: {result1} {ui1.errors}")

            result2, ui2 = run_push("EXPORT v2")
            if not result2:
                ok = False
                details.append(f"second push failed (collision regression): {ui2.errors}")
            elif result2.get("branch") != "fusion-export/TestDesign-2":
                ok = False
                details.append(f"expected uniquified name, got {result2.get('branch')}")
            else:
                pushed = git_run(
                    origin, "show", "fusion-export/TestDesign-2:model.step", check=False
                )
                if pushed.returncode != 0 or pushed.stdout.strip() != "EXPORT v2":
                    ok = False
                    details.append(f"pushed content wrong: {pushed.stdout!r}")

            self.record_result(
                "T_PIPE_07", "Pipeline: template branch uniquify", ok, "; ".join(details)
            )
        except Exception as e:
            self.record_result("T_PIPE_07", "Pipeline: template branch uniquify", False, str(e))
        finally:
            self._cleanup_dir(base_dir)

    def run_pipeline_tests(self):
        """Run git pipeline integration tests."""
        print("\n=== Pipeline Integration Tests ===")
        # Give git an identity via environment variables so commits work on
        # machines/CI runners without user.name/user.email configured, and so
        # the tests never touch the user's global git config.
        identity = {
            "GIT_AUTHOR_NAME": "FusionToGitHub Tests",
            "GIT_AUTHOR_EMAIL": "tests@example.invalid",
            "GIT_COMMITTER_NAME": "FusionToGitHub Tests",
            "GIT_COMMITTER_EMAIL": "tests@example.invalid",
        }
        saved = {key: os.environ.get(key) for key in identity}
        os.environ.update(identity)
        try:
            self.test_pipeline_first_export()
            self.test_pipeline_reexport_changed_file()
            self.test_pipeline_conflict_recovery()
            self.test_pipeline_new_repo_bootstrap()
            self.test_pipeline_cli_end_to_end()
            self.test_pipeline_branch_override_reuse()
            self.test_pipeline_template_branch_uniquify()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

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
        self.test_dialog_helpers_url_functions()
        self.test_askpass_script_security()

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
        self.run_pipeline_tests()

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
                       choices=["pre-install", "core-modules", "git-ops", "cli", "pipeline", "all"],
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
    
    print("FusionToGitHub V7.7 - Automated Test Runner")
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
    elif args.category == "pipeline":
        runner.run_pipeline_tests()
    else:  # all
        runner.run_all_tests()
    
    runner.print_summary()
    
    # Exit with error code if any tests failed
    failed_count = sum(1 for r in runner.results if not r.passed)
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    main()