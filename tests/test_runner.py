#!/usr/bin/env python3
"""
FusionToGitHub - Automated Test Runner

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
import json
import re
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


class _RecordingConfirmUI(_PipelineTestUI):
    """GitUI double that also records the questions it was asked."""

    def __init__(self, answer: bool = True):
        super().__init__(confirm_answer=answer)
        self.questions: List[str] = []

    def confirm(self, message: str) -> bool:
        self.questions.append(message)
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
            # The manifest version is the single source of truth (decision Q4);
            # T_VERSION and T_RELEASE check that this constant matches it. Here
            # we only assert it is set and shaped like a semantic version.
            version_ok = bool(re.match(r"^\d+\.\d+(?:\.\d+)?$", fusion_git_core.VERSION))
            msg = f"Version: {fusion_git_core.VERSION}"
            self.record_result("T004", "fusion_git_core module import", version_ok, msg)
        except Exception as e:
            self.record_result("T004", "fusion_git_core module import", False, str(e))

    def test_t_version_consistency(self):
        """T_VERSION: every user-visible version surface matches the manifest version"""
        self.log_test_start("T_VERSION", "version consistency across all surfaces")
        try:
            import fusion_git_core
            v = fusion_git_core.VERSION
            root = Path(__file__).resolve().parent.parent
            failures = []

            # 1. Add-in manifest
            manifest = json.loads((root / "src" / "Push_To_GitHub.manifest").read_text(encoding="utf-8"))
            if manifest.get("version") != v:
                failures.append(f"manifest version {manifest.get('version')!r} != {v!r}")

            # 2. Push_To_GitHub.py re-exports the core constant, not a literal
            main_src = (root / "src" / "Push_To_GitHub.py").read_text(encoding="utf-8")
            if "VERSION = CORE_VERSION" not in main_src:
                failures.append("Push_To_GitHub.py does not derive VERSION from CORE_VERSION")

            # 3. CLI --version reports it
            ok, out = self.run_command(
                [sys.executable, str(root / "src" / "push_cli.py"), "--version"]
            )
            if v not in out:
                failures.append(f"push_cli --version output {out.strip()!r} lacks {v!r}")

            # 4. No stale internal label anywhere in shipped code
            for py in (root / "src").glob("*.py"):
                if re.search(r"\bV7\.7\b", py.read_text(encoding="utf-8")):
                    failures.append(f"stale 'V7.7' in {py.name}")

            # 5. README and the docs index state the current version and nothing older
            readme = (root / "README.md").read_text(encoding="utf-8")
            if f"**`{v}`**" not in readme and f"`{v}`" not in readme:
                failures.append("README does not state the current version")
            if re.search(r"\bV7\.7\b", readme):
                failures.append("stale 'V7.7' in README.md")

            self.record_result(
                "T_VERSION", "version consistency", not failures, "; ".join(failures)
            )
        except Exception as e:
            self.record_result("T_VERSION", "version consistency", False, str(e))

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
                ("github.com/user/repo.git", "https://github.com/user/repo.git"),
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

    def test_credential_scoping(self):
        """T_CORE_03: the stored token goes only to the origin's https host, and no helper keeps a copy.

        Regression for audit SEC-02/04 (experiment S-E8): a pre-configured
        `store` helper must stay empty, another host must get nothing, and
        plain http must be refused.
        """
        self.log_test_start("T_CORE_03", "Stored-token credential scoping")
        base = tempfile.mkdtemp(prefix="fusion_cred_")
        try:
            from fusion_git_core import GitError, git_run, token_auth

            problems = []
            # Never let these credential commands reach the developer's real
            # helpers (e.g. Git Credential Manager): no system or global
            # config, and hosts that can't match a real stored credential.
            empty_global = os.path.join(base, "empty.gitconfig")
            open(empty_global, "w").close()
            isolated = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": empty_global}
            host = "git.example.invalid"
            repo = os.path.join(base, "repo")
            git_run(base, "init", repo, env=isolated)
            store_file = os.path.join(base, "store.txt").replace("\\", "/")
            git_run(repo, "config", "credential.helper", f"store --file={store_file}", env=isolated)
            token = "ghp_" + "T" * 36
            from dataclasses import replace as dc_replace

            no_hooks = os.path.join(base, "nohooks")
            os.makedirs(no_hooks)
            # push_export always gives the token an empty hooks folder (R-21).
            auth = dc_replace(token_auth(f"https://{host}/owner/repo.git", token), hooks_dir=no_hooks)

            fill = git_run(repo, "credential", "fill", check=False, auth=auth, env=isolated,
                           input_text=f"protocol=https\nhost={host}\n\n")
            if fill.returncode != 0 or f"password={token}" not in fill.stdout:
                problems.append(f"helper did not answer for {host}: rc={fill.returncode}")
            other = git_run(repo, "credential", "fill", check=False, auth=auth, env=isolated,
                            input_text="protocol=https\nhost=evil.example.invalid\n\n")
            if token in other.stdout:
                problems.append("token offered to another host")
            git_run(repo, "credential", "approve", check=False, auth=auth, env=isolated,
                    input_text=fill.stdout + "\n")
            if os.path.exists(store_file) and os.path.getsize(store_file) > 0:
                problems.append("another credential helper stored a copy of the token")
            if "FUSION_GIT_TOKEN" in repr(auth) or token in repr(auth):
                problems.append("token visible in repr()")
            for bad_url in ("http://github.com/owner/repo.git", "git@github.com:owner/repo.git"):
                try:
                    token_auth(bad_url, token)
                    problems.append(f"token allowed for {bad_url}")
                except GitError:
                    pass
            # A local git call without auth must not see the token.
            plain = git_run(repo, "config", "--get-all", "credential.helper", check=False)
            if token in plain.stdout:
                problems.append("token leaked into config")
            self.record_result("T_CORE_03", "Stored-token credential scoping", not problems, "; ".join(problems))
        except Exception as e:
            self.record_result("T_CORE_03", "Stored-token credential scoping", False, str(e))
        finally:
            self._cleanup_dir(base)

    def test_secret_redaction_and_urls(self):
        """T_CORE_05: tokens in URLs are refused and redacted everywhere (audit SEC-03)."""
        self.log_test_start("T_CORE_05", "Token-in-URL refusal and redaction")
        base = tempfile.mkdtemp(prefix="fusion_redact_")
        try:
            from dialog_helpers import publication_notice, setup_new_repository, validate_repo_inputs
            from fusion_git_core import git_run, redact_secrets, url_has_embedded_secret

            problems = []
            token = "ghp_" + "S" * 36
            fine_grained = "github_pat_" + "A" * 30
            cases = {
                f"https://user:{token}@github.com/o/r.git": True,
                f"https://{token}@github.com/o/r.git": True,
                "https://user:hunter2@example.com/o/r.git": True,
                "https://user@github.com/o/r.git": False,
                "git@github.com:o/r.git": False,
                "https://github.com/o/r.git": False,
            }
            for url, expected in cases.items():
                if url_has_embedded_secret(url) != expected:
                    problems.append(f"url_has_embedded_secret({redact_secrets(url)!r}) != {expected}")

            text = f"fatal: unable to access 'https://bob:{token}@github.com/o/r.git/' {fine_grained} and mytoken99"
            redacted = redact_secrets(text, ["mytoken99"])
            for secret in (token, fine_grained, "mytoken99", "bob:"):
                if secret in redacted:
                    problems.append(f"{secret[:8]}… not redacted")

            bad_url = f"https://user:{token}@github.com/o/r.git"
            add_new = "__add_new__"
            check = validate_repo_inputs(add_new, os.path.join(base, "x"), bad_url, add_new)
            if check["ok"] or "token" not in check["messages"]["git"][0]:
                problems.append("the dialog accepted a URL with a token")
            if not setup_new_repository("x", os.path.join(base, "x"), bad_url, git_run):
                problems.append("setup accepted a URL with a token")
            if os.path.exists(os.path.join(base, "x", ".git")):
                problems.append("setup created a repository for a URL with a token")

            notice = publication_notice("https://github.com/acme/widgets.git")
            if "github.com/acme/widgets" not in notice or "public" not in notice:
                problems.append(f"publication notice unclear: {notice[:80]!r}")
            if "github.com/acme/widgets" not in publication_notice("git@github.com:acme/widgets.git"):
                problems.append("publication notice wrong for ssh addresses")

            cli_help = self.run_command([sys.executable, str(Path("src") / "push_cli.py"), "--help"])[1]
            if "--pat-token" in cli_help:
                problems.append("push_cli still accepts a token on the command line")
            self.record_result("T_CORE_05", "Token-in-URL refusal and redaction", not problems, "; ".join(problems))
        except Exception as e:
            self.record_result("T_CORE_05", "Token-in-URL refusal and redaction", False, str(e))
        finally:
            self._cleanup_dir(base)

    def test_export_subfolder_helpers(self):
        """T_CORE_04: subfolder normalisation, placeholder expansion, containment"""
        self.log_test_start("T_CORE_04", "Export subfolder helpers")
        base = None
        try:
            from dialog_helpers import (
                expand_export_subfolder,
                normalize_export_subfolder,
            )

            failures = []

            norm_cases = [
                ("exports/", "exports"),
                ("exports\\step", "exports/step"),
                ("  ", ""),
                ("{filename}/v{timestamp}", "{filename}/v{timestamp}"),
            ]
            for raw, expected in norm_cases:
                result = normalize_export_subfolder(raw)
                if result != expected:
                    failures.append(f"normalize {raw!r} -> {result!r} (expected {expected!r})")
            for bad in ("../up", "a/../b", "/absolute", "bad|segment"):
                try:
                    normalize_export_subfolder(bad)
                    failures.append(f"normalize accepted invalid input {bad!r}")
                except ValueError:
                    pass

            expanded = expand_export_subfolder(
                "exports/{filename}/v{timestamp}", "Bracket V2", "20260708-120000"
            )
            if expanded != "exports/Bracket V2/v20260708-120000":
                failures.append(f"expansion wrong: {expanded!r}")
            if expand_export_subfolder("", "X") != "":
                failures.append("blank template should stay blank")
            if expand_export_subfolder("plain/folder", "X") != "plain/folder":
                failures.append("template without placeholders should be unchanged")
            # A generated timestamp is used when none is supplied.
            auto = expand_export_subfolder("v{timestamp}", "X")
            if not (auto.startswith("v") and len(auto) == len("v20260708-120000")):
                failures.append(f"auto timestamp expansion wrong: {auto!r}")

            self.record_result(
                "T_CORE_04", "Export subfolder helpers", not failures, "; ".join(failures)
            )
        except Exception as e:
            self.record_result("T_CORE_04", "Export subfolder helpers", False, str(e))
        finally:
            self._cleanup_dir(base)

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
                git_run(temp_dir, "-c", "commit.gpgSign=false", "commit", "-m", "Test commit")
                
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
            
            self._cleanup_dir(temp_dir)

    # CLI Tests
    def test_cli_basic_functionality(self):
        """Test CLI harness basic functionality"""
        self.log_test_start("T_CLI_01", "CLI basic functionality")
        
        # Test help display  
        cli_path = Path("src") / "push_cli.py"
        success, output = self.run_command([sys.executable, str(cli_path), "--help"])
        help_ok = success and all(word in output.lower() for word in ["usage", "options"])

        # Standalone execution (risk R-25): the CLI also runs as a plain script
        # without the add-in package (-E -s: no PYTHON* variables and no user
        # site-packages, so only its own folder is on sys.path).
        isolated_ok, isolated_out = self.run_command([sys.executable, "-E", "-s", str(cli_path), "--help"])
        from fusion_git_core import VERSION
        version_ok = (
            isolated_ok and "usage" in isolated_out.lower()
            and isinstance(VERSION, str) and bool(re.match(r"^\d+\.\d+\.\d+$", VERSION))
        )

        overall_ok = version_ok and help_ok
        msg = f"Version import OK: {version_ok}, Help OK: {help_ok}"
        self.record_result("T_CLI_01", "CLI basic functionality", overall_ok, msg)

    # Pipeline Integration Tests
    #
    # These exercise fusion_git_core.push_export end-to-end against local bare
    # repositories. Every push test also checks invariant I1: the user's
    # working tree, index, stash, HEAD and local refs are exactly as before.

    @staticmethod
    def _cleanup_dir(path: Optional[str]):
        """Delete a test folder, including Git's read-only object files (Windows)."""
        import stat

        def clear_readonly(func, target, _exc):
            try:
                os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
                func(target)
            except OSError:
                pass

        for attempt in range(5):
            if not path or not os.path.exists(path):
                return
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=clear_readonly)
            else:
                shutil.rmtree(path, onerror=clear_readonly)
            if os.path.exists(path):
                time.sleep(0.3)

    @staticmethod
    def _make_seeded_remote(base_dir: str):
        """Create a bare origin plus a work clone with one pushed commit.

        Fixture commits opt out of commit signing, so the suite also runs under
        tests/hostile.gitconfig (which turns signing on); the add-in's own
        commits use git commit-tree, which never signs.

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
        git_run(work, "-c", "commit.gpgSign=false", "commit", "-m", "seed commit")
        git_run(work, "remote", "add", "origin", origin)
        git_run(work, "push", "-u", "origin", branch)
        # Make origin's HEAD point at the seeded branch whatever git's default is.
        git_run(origin, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
        return origin, work, branch

    @staticmethod
    def _write_export(base_dir: str, name: str, content) -> str:
        """Write an export file outside the repository, as Fusion's temp export folder would."""
        export_dir = os.path.join(base_dir, "exports")
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, name)
        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    @staticmethod
    def _local_state(work: str) -> dict:
        """Everything invariant I1 says a push must leave alone."""
        import hashlib

        from fusion_git_core import git_run

        files = {}
        for root, dirs, names in os.walk(work):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in names:
                path = os.path.join(root, name)
                with open(path, "rb") as fh:
                    files[os.path.relpath(path, work)] = hashlib.sha256(fh.read()).hexdigest()
        index_path = os.path.join(work, ".git", "index")
        index = None
        if os.path.exists(index_path):
            with open(index_path, "rb") as fh:
                index = hashlib.sha256(fh.read()).hexdigest()
        return {
            "files": files,
            "index": index,
            "head": git_run(work, "symbolic-ref", "-q", "HEAD", check=False).stdout.strip(),
            "head_sha": git_run(work, "rev-parse", "-q", "--verify", "HEAD", check=False).stdout.strip(),
            "local_refs": git_run(
                work, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags", "refs/stash"
            ).stdout,
            "stash": git_run(work, "stash", "list", "--format=%H", check=False).stdout,
            "status": git_run(
                work, "--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all"
            ).stdout,
        }

    def _assert_untouched(self, before: dict, work: str, details: list) -> bool:
        after = self._local_state(work)
        changed = [key for key in before if before[key] != after[key]]
        if changed:
            details.append(f"local repository changed (I1): {changed}")
            return False
        return True

    @staticmethod
    def _push(work, exports, ui, **kwargs):
        from fusion_git_core import push_export

        return push_export(
            work,
            exports,
            kwargs.pop("message", "Design update: {filename}"),
            kwargs.pop("design", "TestDesign"),
            ui,
            **kwargs,
        )

    def _run_pipeline_case(self, test_id: str, name: str, body):
        """Run *body(base_dir, details) -> ok* with cleanup and error capture."""
        self.log_test_start(test_id, name)
        base_dir = tempfile.mkdtemp(prefix=f"fusion_{test_id.lower()}_")
        details: list = []
        try:
            ok = body(base_dir, details)
            self.record_result(test_id, name, bool(ok) and not details, "; ".join(details))
        except Exception as e:
            self.record_result(test_id, name, False, f"{type(e).__name__}: {e}")
        finally:
            self._cleanup_dir(base_dir)

    def test_pipeline_first_export(self):
        """T_PIPE_01: a first export is pushed to a new branch built on GitHub's main."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            export = self._write_export(base_dir, "model.step", "EXPORT v1")
            before = self._local_state(work)
            ui = _PipelineTestUI()
            result = self._push(work, [(export, "model.step")], ui)
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
                return False
            pushed = git_run(origin, "show", f"{result['branch']}:model.step", check=False)
            if pushed.stdout.strip() != "EXPORT v1":
                details.append(f"pushed content wrong: {pushed.stdout!r}")
            main_tip = git_run(origin, "rev-parse", branch).stdout.strip()
            parent = git_run(origin, "rev-parse", f"{result['branch']}^").stdout.strip()
            if parent != main_tip:
                details.append("export is not built on GitHub's main")
            changelog = git_run(origin, "show", f"{result['branch']}:CHANGELOG.md", check=False).stdout
            if "TestDesign" not in changelog:
                details.append("history entry missing")
            self._assert_untouched(before, work, details)
            return True

        self._run_pipeline_case("T_PIPE_01", "Pipeline: first export", body)

    def test_pipeline_reexport_changed_file(self):
        """T_PIPE_02: re-exporting a changed file pushes the new content."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            ui = _PipelineTestUI()
            first = self._push(work, [(self._write_export(base_dir, "model.step", "EXPORT v1"), "model.step")], ui)
            second = self._push(
                work, [(self._write_export(base_dir, "model.step", "EXPORT v2 CHANGED"), "model.step")], ui
            )
            if not (first and second):
                details.append(f"a push failed: {ui.errors}")
                return False
            pushed = git_run(origin, "show", f"{second['branch']}:model.step").stdout.strip()
            if pushed != "EXPORT v2 CHANGED":
                details.append(f"stale content pushed: {pushed!r}")
            return True

        self._run_pipeline_case("T_PIPE_02", "Pipeline: re-export pushes new content", body)

    def test_pipeline_busy_checkout_untouched(self):
        """T_PIPE_03: a dirty, diverged checkout is left alone and its local commits stay private.

        Regression for audit REL-02/05/07/14 and SEC-01 (experiment G-E5).
        """

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            # GitHub moves ahead...
            other = os.path.join(base_dir, "other")
            git_run(base_dir, "clone", origin, other)
            with open(os.path.join(other, "readme.md"), "w", encoding="utf-8") as fh:
                fh.write("remote edit\n")
            git_run(other, "-c", "commit.gpgSign=false", "commit", "-am", "remote edit")
            git_run(other, "push", "origin", branch)
            # ...while the user has a private unpushed commit, a staged change,
            # an unstaged change and an untracked file.
            with open(os.path.join(work, "secret.txt"), "w", encoding="utf-8") as fh:
                fh.write("private work\n")
            git_run(work, "add", "secret.txt")
            git_run(work, "-c", "commit.gpgSign=false", "commit", "-m", "private unpushed commit")
            with open(os.path.join(work, "staged.txt"), "w", encoding="utf-8") as fh:
                fh.write("staged\n")
            git_run(work, "add", "staged.txt")
            with open(os.path.join(work, "readme.md"), "w", encoding="utf-8") as fh:
                fh.write("local uncommitted edit\n")
            with open(os.path.join(work, "scrap.txt"), "w", encoding="utf-8") as fh:
                fh.write("precious uncommitted data")

            before = self._local_state(work)
            ui = _PipelineTestUI()
            result = self._push(work, [(self._write_export(base_dir, "model.step", "EXPORT vX"), "model.step")], ui)
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
                return False
            tree = git_run(origin, "ls-tree", "-r", "--name-only", result["branch"]).stdout.split()
            if "secret.txt" in tree:
                details.append("a private local commit was published (SEC-01)")
            log = git_run(origin, "log", "--format=%s", result["branch"]).stdout
            if "private unpushed commit" in log:
                details.append("local-only commit reached GitHub (I3)")
            if "remote edit" not in log:
                details.append("export not built on GitHub's latest main")
            self._assert_untouched(before, work, details)
            return True

        self._run_pipeline_case("T_PIPE_03", "Pipeline: busy checkout untouched, local commits private", body)

    def test_pipeline_new_repo_bootstrap(self):
        """T_PIPE_04: setup + first push into an empty GitHub repository."""

        def body(base_dir, details):
            from dialog_helpers import setup_new_repository
            from fusion_git_core import git_run

            origin = os.path.join(base_dir, "origin.git")
            git_run(base_dir, "init", "--bare", origin)
            local_path = os.path.join(base_dir, "MyNewRepo")
            error = setup_new_repository("MyNewRepo", local_path, origin, git_run)
            if error:
                details.append(error)
                return False
            ui = _PipelineTestUI()
            result = self._push(local_path, [(self._write_export(base_dir, "model.step", "FIRST"), "model.step")], ui)
            if not result:
                details.append(f"pipeline failed: {ui.errors}")
                return False
            if not result.get("bootstrapped"):
                details.append("empty repository was not bootstrapped")
            main_files = git_run(origin, "ls-tree", "--name-only", "main", check=False).stdout.split()
            if main_files != [".gitattributes"]:
                details.append(f"main should hold only .gitattributes, has {main_files}")
            if git_run(origin, "show", f"{result['branch']}:model.step").stdout.strip() != "FIRST":
                details.append("export content wrong")
            if git_run(origin, "rev-parse", f"{result['branch']}^").stdout.strip() != git_run(
                origin, "rev-parse", "main"
            ).stdout.strip():
                details.append("export is not built on the new main")
            return True

        self._run_pipeline_case("T_PIPE_04", "Pipeline: empty repository bootstrap", body)

    def test_pipeline_cli_end_to_end(self):
        """T_PIPE_05: push_cli pushes a file and leaves the checkout alone."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            with open(os.path.join(work, "model.step"), "w", encoding="utf-8") as fh:
                fh.write("CLI EXPORT")
            before = self._local_state(work)
            cli_path = Path("src") / "push_cli.py"
            success, output = self.run_command(
                [sys.executable, str(cli_path), "--repo", work, "--files", "model.step", "--design-name", "CliDesign"]
            )
            if not success:
                details.append(output)
                return False
            branches = git_run(origin, "branch", "--format", "%(refname:short)").stdout
            export_branch = next((b.strip() for b in branches.splitlines() if "fusion-export" in b), None)
            if not export_branch:
                details.append(f"no export branch on origin: {branches}")
            elif git_run(origin, "show", f"{export_branch}:model.step").stdout.strip() != "CLI EXPORT":
                details.append("pushed content wrong")
            self._assert_untouched(before, work, details)
            ok_missing, out_missing = self.run_command(
                [sys.executable, str(cli_path), "--repo", work, "--files", "nope.step"], expect_success=False
            )
            if not ok_missing:
                details.append("a missing file should make the CLI fail")
            return True

        self._run_pipeline_case("T_PIPE_05", "Pipeline: CLI end-to-end", body)

    def test_pipeline_branch_override_reuse(self):
        """T_PIPE_06: pushing twice to the same override branch appends; declining cancels."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            before = self._local_state(work)

            def push(content, answer=True):
                ui = _PipelineTestUI(confirm_answer=answer)
                export = self._write_export(base_dir, "model.step", content)
                return self._push(work, [(export, "model.step")], ui, branch_override="my-export"), ui

            first, ui1 = push("EXPORT v1")
            if not first or first.get("reused_branch"):
                details.append(f"first push wrong: {first} {ui1.errors}")
            second, ui2 = push("EXPORT v2")
            if not second or not second.get("reused_branch"):
                details.append(f"second push should reuse the branch: {second} {ui2.errors}")
            count = git_run(origin, "rev-list", "--count", "my-export").stdout.strip()
            if count != "3":  # seed + 2 exports
                details.append(f"expected 3 commits on my-export, got {count}")
            third, ui3 = push("EXPORT v3", answer=False)
            if not (third and third.get("cancelled")) or ui3.errors:
                details.append(f"declined reuse should cancel cleanly: {third} {ui3.errors}")
            if git_run(origin, "rev-list", "--count", "my-export").stdout.strip() != "3":
                details.append("declined push changed GitHub")
            self._assert_untouched(before, work, details)
            return True

        self._run_pipeline_case("T_PIPE_06", "Pipeline: branch override reuse", body)

    def test_pipeline_template_branch_uniquify(self):
        """T_PIPE_07: a template name that already exists on GitHub gets a suffix."""

        def body(base_dir, details):
            ui = _PipelineTestUI()
            origin, work, branch = self._make_seeded_remote(base_dir)
            names = []
            for content in ("EXPORT v1", "EXPORT v2"):
                export = self._write_export(base_dir, "model.step", content)
                result = self._push(work, [(export, "model.step")], ui, branch_format_str="fusion-export/{filename}")
                names.append(result and result["branch"])
            if names != ["fusion-export/TestDesign", "fusion-export/TestDesign-2"]:
                details.append(f"unexpected branch names {names} {ui.errors}")
            return True

        self._run_pipeline_case("T_PIPE_07", "Pipeline: template branch uniquify", body)

    def test_pipeline_reused_branch_builds_on_remote_tip(self):
        """T_PIPE_08: an override branch updated elsewhere keeps those commits."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            ui = _PipelineTestUI()
            self._push(work, [(self._write_export(base_dir, "model.step", "v1"), "model.step")], ui,
                       branch_override="my-export")
            other = os.path.join(base_dir, "other")
            git_run(base_dir, "clone", "--branch", "my-export", origin, other)
            with open(os.path.join(other, "notes.txt"), "w", encoding="utf-8") as fh:
                fh.write("added elsewhere\n")
            git_run(other, "add", "notes.txt")
            git_run(other, "-c", "commit.gpgSign=false", "commit", "-m", "remote-side commit")
            git_run(other, "push", "origin", "my-export")
            result = self._push(work, [(self._write_export(base_dir, "model.step", "v2"), "model.step")], ui,
                                branch_override="my-export")
            if not result:
                details.append(f"second push failed: {ui.errors}")
                return False
            if git_run(origin, "show", "my-export:notes.txt", check=False).stdout.strip() != "added elsewhere":
                details.append("remote-side commit was lost")
            if git_run(origin, "show", "my-export:model.step").stdout.strip() != "v2":
                details.append("new export missing")
            return True

        self._run_pipeline_case("T_PIPE_08", "Pipeline: reused branch builds on GitHub's tip", body)

    def test_pipeline_never_overwrites_remote(self):
        """T_PIPE_09: concurrent and hook-rejected pushes never overwrite GitHub.

        Regression for audit REL-01 (G-E7c, G-E7d'). Every confirmation is
        accepted, the worst case for the old force-push behaviour.
        """

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)

            def colleague_commit(target_branch, filename, content, create=False):
                other = os.path.join(base_dir, f"other-{len(os.listdir(base_dir))}")
                if create:
                    git_run(base_dir, "clone", origin, other)
                    git_run(other, "checkout", "-b", target_branch)
                else:
                    git_run(base_dir, "clone", "--branch", target_branch, origin, other)
                with open(os.path.join(other, filename), "w", encoding="utf-8") as fh:
                    fh.write(content)
                git_run(other, "add", filename)
                git_run(other, "-c", "commit.gpgSign=false", "commit", "-m", f"colleague edit on {target_branch}")
                git_run(other, "push", "origin", target_branch)
                return git_run(origin, "rev-parse", target_branch).stdout.strip()

            def is_ancestor(old, new_ref):
                return git_run(origin, "merge-base", "--is-ancestor", old, new_ref, check=False).returncode == 0

            # Case A (G-E7c): the override names a branch that only GitHub has.
            shared_tip = colleague_commit("shared-export", "colleague.txt", "theirs\n", create=True)
            git_run(work, "fetch", "origin")
            ui_a = _PipelineTestUI()
            result_a = self._push(work, [(self._write_export(base_dir, "a.step", "A"), "a.step")], ui_a,
                                  branch_override="shared-export")
            if not result_a:
                details.append(f"case A failed: {ui_a.errors}")
            elif not is_ancestor(shared_tip, "shared-export"):
                details.append("case A: colleague's commit was overwritten")

            # Case B: a colleague pushes between our commit being built and pushed.
            self._push(work, [(self._write_export(base_dir, "m.step", "v1"), "m.step")], _PipelineTestUI(),
                       branch_override="my-export")
            raced = {}

            def race(step_text):
                if step_text.startswith("Pushing") and not raced:
                    raced["tip"] = colleague_commit("my-export", "colleague.txt", "raced\n")

            ui_b = _PipelineTestUI()
            result_b = self._push(work, [(self._write_export(base_dir, "m.step", "v2"), "m.step")], ui_b,
                                  branch_override="my-export", on_step=race)
            if not result_b:
                details.append(f"case B failed: {ui_b.errors}")
            else:
                if result_b.get("attempts") != 2:
                    details.append(f"case B: expected a rebuild after the race, attempts={result_b.get('attempts')}")
                if not is_ancestor(raced["tip"], "my-export"):
                    details.append("case B: the colleague's raced commit was overwritten")

            # Case C: GitHub refuses the push (server-side hook): no retries, nothing changes.
            hook = os.path.join(origin, "hooks", "pre-receive")
            with open(hook, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("#!/bin/sh\necho 'policy says no' >&2\nexit 1\n")
            os.chmod(hook, 0o755)
            tip_before = git_run(origin, "rev-parse", "my-export").stdout.strip()
            ui_c = _PipelineTestUI()
            result_c = self._push(work, [(self._write_export(base_dir, "m.step", "v3"), "m.step")], ui_c,
                                  branch_override="my-export")
            if result_c:
                details.append(f"case C: a rejected push reported success: {result_c}")
            if not any("Nothing on GitHub was changed" in e for e in ui_c.errors):
                details.append(f"case C: unclear failure message: {ui_c.errors}")
            if git_run(origin, "rev-parse", "my-export").stdout.strip() != tip_before:
                details.append("case C: GitHub changed")
            return True

        self._run_pipeline_case("T_PIPE_09", "Pipeline: never overwrites remote commits", body)

    def test_pipeline_single_history(self):
        """T_PIPE_10: single-history mode adds each export to the default branch."""

        def body(base_dir, details):
            from fusion_git_core import MODE_SINGLE, git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            before = self._local_state(work)
            ui = _PipelineTestUI()
            for content in ("v1", "v2"):
                export = self._write_export(base_dir, "Bracket.step", content)
                result = self._push(work, [(export, "designs/Bracket/Bracket.step")], ui, mode=MODE_SINGLE,
                                    design="Bracket")
                if not result or result["branch"] != branch:
                    details.append(f"push went to {result and result['branch']} not {branch}: {ui.errors}")
                    return False
            count = git_run(origin, "rev-list", "--count", branch).stdout.strip()
            if count != "3":
                details.append(f"expected 3 commits on {branch}, got {count}")
            if git_run(origin, "show", f"{branch}:designs/Bracket/Bracket.step").stdout.strip() != "v2":
                details.append("latest export not on the default branch")
            changelog = git_run(origin, "show", f"{branch}:CHANGELOG.md").stdout
            if changelog.count("## ") != 2:
                details.append("history file should have two entries")
            branches = git_run(origin, "branch", "--format", "%(refname:short)").stdout.split()
            if branches != [branch]:
                details.append(f"single mode created extra branches: {branches}")
            self._assert_untouched(before, work, details)
            return True

        self._run_pipeline_case("T_PIPE_10", "Pipeline: single history", body)

    def test_pipeline_default_branch_override_warns(self):
        """T_PIPE_11: overriding to the main branch asks a distinct question (audit UX-09)."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            tip = git_run(origin, "rev-parse", branch).stdout.strip()
            ui = _RecordingConfirmUI(answer=False)
            result = self._push(work, [(self._write_export(base_dir, "m.step", "x"), "m.step")], ui,
                                branch_override=branch)
            if not (result and result.get("cancelled")):
                details.append(f"declining should cancel: {result}")
            if not any("main branch" in q for q in ui.questions):
                details.append(f"no main-branch warning: {ui.questions}")
            if git_run(origin, "rev-parse", branch).stdout.strip() != tip:
                details.append("GitHub changed after declining")
            return True

        self._run_pipeline_case("T_PIPE_11", "Pipeline: main-branch override warns", body)

    def test_pipeline_timeout(self):
        """T_PIPE_12: a hung push is stopped by its timeout (audit REL-06)."""

        def body(base_dir, details):
            import fusion_git_core
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            hook = os.path.join(origin, "hooks", "pre-receive")
            with open(hook, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("#!/bin/sh\nsleep 60\nexit 1\n")
            os.chmod(hook, 0o755)
            saved = dict(fusion_git_core.TIMEOUTS)
            fusion_git_core.TIMEOUTS["network"] = 4
            try:
                ui = _PipelineTestUI()
                started = time.time()
                result = self._push(work, [(self._write_export(base_dir, "m.step", "x"), "m.step")], ui)
                elapsed = time.time() - started
            finally:
                fusion_git_core.TIMEOUTS.update(saved)
            if result:
                details.append("a hung push reported success")
            if elapsed > 30:
                details.append(f"timeout not enforced: took {elapsed:.0f}s")
            if not any("took longer than" in e for e in ui.errors):
                details.append(f"no timeout message: {ui.errors}")
            heads = git_run(origin, "branch", "--format", "%(refname:short)").stdout.split()
            if heads != [branch]:
                details.append(f"GitHub changed: {heads}")
            return True

        self._run_pipeline_case("T_PIPE_12", "Pipeline: hung push times out", body)

    def test_pipeline_size_gate(self):
        """T_PIPE_13: exports of 100 MB+ are refused before any git command; large ones need consent."""

        def body(base_dir, details):
            import fusion_git_core

            origin, work, branch = self._make_seeded_remote(base_dir)
            big = os.path.join(base_dir, "exports", "huge.stl")
            os.makedirs(os.path.dirname(big), exist_ok=True)
            with open(big, "wb") as fh:  # sparse: fast, but reports 100 MB
                fh.seek(fusion_git_core.SIZE_BLOCK_BYTES)
                fh.write(b"x")
            ui = _PipelineTestUI()
            if self._push(work, [(big, "huge.stl")], ui) or not any("100 MB" in e for e in ui.errors):
                details.append(f"100 MB export not refused: {ui.errors}")

            saved = fusion_git_core.SIZE_WARN_BYTES
            fusion_git_core.SIZE_WARN_BYTES = 10
            try:
                ui2 = _PipelineTestUI(confirm_answer=False)
                result = self._push(work, [(self._write_export(base_dir, "m.step", "x" * 50), "m.step")], ui2)
            finally:
                fusion_git_core.SIZE_WARN_BYTES = saved
            if not (result and result.get("cancelled")):
                details.append(f"declining the large-file warning should cancel: {result}")
            from fusion_git_core import git_run

            if git_run(origin, "branch", "--format", "%(refname:short)").stdout.split() != [branch]:
                details.append("GitHub changed")
            return True

        self._run_pipeline_case("T_PIPE_13", "Pipeline: size gate", body)

    def test_pipeline_non_ascii(self):
        """T_PIPE_14: non-ASCII design names, messages and identities (audit REL-03)."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            ui = _PipelineTestUI()
            saved = {k: os.environ.get(k) for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")}
            os.environ["GIT_AUTHOR_NAME"] = os.environ["GIT_COMMITTER_NAME"] = "Łukasz Żółć"
            try:
                export = self._write_export(base_dir, "Teil.step", "ä ö ü")
                result = self._push(
                    work,
                    [(export, "designs/Halterung für Motor/Teil.step")],
                    ui,
                    design="Halterung für Motor",
                    message="Bohrung vergrößert — {filename}",
                    mode="single",
                )
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            if not result:
                details.append(f"push failed: {ui.errors}")
                return False
            subject = git_run(origin, "log", "-1", "--format=%s", branch).stdout.strip()
            if subject != "Bohrung vergrößert — Halterung für Motor":
                details.append(f"commit message mangled: {subject!r}")
            author = git_run(origin, "log", "-1", "--format=%an", branch).stdout.strip()
            if author != "Łukasz Żółć":
                details.append(f"author mangled: {author!r}")
            files = git_run(origin, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", branch).stdout
            if "designs/Halterung für Motor/Teil.step" not in files:
                details.append(f"path mangled: {files!r}")
            return True

        self._run_pipeline_case("T_PIPE_14", "Pipeline: non-ASCII names", body)

    def test_pipeline_history_bytes_preserved(self):
        """T_PIPE_15: the history file keeps its line endings and any non-UTF-8 bytes."""

        def body(base_dir, details):
            from fusion_git_core import MODE_SINGLE, git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            other = os.path.join(base_dir, "other")
            git_run(base_dir, "clone", origin, other)
            with open(os.path.join(other, "CHANGELOG.md"), "wb") as fh:
                fh.write(b"# Changelog\r\n\r\nold entry caf\xe9\r\n")
            git_run(other, "-c", "core.autocrlf=false", "add", "CHANGELOG.md")
            git_run(other, "-c", "commit.gpgSign=false", "commit", "-m", "add changelog")
            git_run(other, "push", "origin", branch)
            ui = _PipelineTestUI()
            result = self._push(work, [(self._write_export(base_dir, "m.step", "x"), "m.step")], ui, mode=MODE_SINGLE)
            if not result:
                details.append(f"push failed: {ui.errors}")
                return False
            blob = subprocess.run(
                ["git", "cat-file", "blob", f"{branch}:CHANGELOG.md"], cwd=origin, capture_output=True
            ).stdout
            if not blob.endswith(b"old entry caf\xe9\r\n"):
                details.append("existing history bytes changed")
            if b"\n" in blob.replace(b"\r\n", b""):
                details.append("history file has mixed line endings")
            return True

        self._run_pipeline_case("T_PIPE_15", "Pipeline: history file bytes preserved", body)

    def test_pipeline_rejects_bad_paths_and_names(self):
        """T_PIPE_16: unsafe paths and option-like branch names never reach git (audit BUG-08)."""

        def body(base_dir, details):
            from fusion_git_core import is_valid_branch_name, normalize_repo_path, sanitize_branch_name

            for raw, expected in [("-n", "n"), ("--force", "force"), ("a..b", "a.b"), ("x.lock", "x"),
                                  ("feature/test", "feature/test")]:
                if sanitize_branch_name(raw) != expected:
                    details.append(f"sanitize({raw!r}) = {sanitize_branch_name(raw)!r}")
            for name, valid in [("-x", False), ("a..b", False), ("ok/name", True), ("x.lock", False)]:
                if is_valid_branch_name(name) != valid:
                    details.append(f"is_valid_branch_name({name!r}) should be {valid}")
            for bad in ["../escape.step", "/abs.step", "C:/abs.step", ".git/config", ""]:
                try:
                    normalize_repo_path(bad)
                    details.append(f"path {bad!r} was accepted")
                except ValueError:
                    pass
            if normalize_repo_path("a\\b/./c.step") != "a/b/c.step":
                details.append("path not normalised")
            origin, work, branch = self._make_seeded_remote(base_dir)
            ui = _PipelineTestUI()
            if self._push(work, [(self._write_export(base_dir, "m.step", "x"), "../m.step")], ui):
                details.append("an export path outside the repository was pushed")
            return True

        self._run_pipeline_case("T_PIPE_16", "Pipeline: unsafe paths and names refused", body)

    def test_pipeline_token_requires_https(self):
        """T_PIPE_17: a stored token is never sent over a non-https remote; errors are redacted."""

        def body(base_dir, details):
            from fusion_git_core import git_run

            origin, work, branch = self._make_seeded_remote(base_dir)
            token = "ghp_" + "P" * 36
            ui = _PipelineTestUI()
            result = self._push(work, [(self._write_export(base_dir, "m.step", "x"), "m.step")], ui,
                                pat_credentials={"username": "", "token": token})
            if result:
                details.append("a token was used with a non-https remote")
            if not any("https" in e for e in ui.errors):
                details.append(f"no explanation: {ui.errors}")
            if any(token in e for e in ui.errors + ui.warnings):
                details.append("token appeared in a message")
            if git_run(origin, "branch", "--format", "%(refname:short)").stdout.split() != [branch]:
                details.append("GitHub changed")

            # An origin URL that embeds a token is pushed to, but warned about,
            # and the token never appears in messages.
            git_run(work, "remote", "set-url", "origin", origin)
            ui2 = _PipelineTestUI()
            git_run(work, "config", "remote.origin.pushurl", f"https://u:{token}@127.0.0.1:9/none.git")
            self._push(work, [(self._write_export(base_dir, "m.step", "x"), "m.step")], ui2)
            if not any("plain text" in w for w in ui2.warnings):
                details.append(f"no warning about a token in the address: {ui2.warnings}")
            if any(token in m for m in ui2.errors + ui2.warnings):
                details.append("token from the address appeared in a message")
            return True

        self._run_pipeline_case("T_PIPE_17", "Pipeline: token needs https; secrets redacted", body)

    def test_setup_blank_name_uses_clone_folder(self):
        """T_SETUP_01: "Set up new" with a blank name pushes from the folder it cloned into.

        Regression test for audit finding BUG-01. The dialog validates the
        suggested folder (…/NewRepo) before the name is derived from the URL;
        the add-in then cloned into …/<name> but pushed from …/NewRepo.
        """

        def body(base_dir, details):
            from dialog_helpers import (
                default_path_for_new_repo,
                derive_repo_name_from_url,
                resolve_new_repo_path,
                setup_new_repository,
                validate_repo_inputs,
            )
            from fusion_git_core import git_run

            def safe_base(name):
                return re.sub(r"[^\w\-]", "_", name)

            add_new = "__add_new__"
            repos_dir = os.path.join(base_dir, "FusionGitRepos")
            origin_dir = os.path.join(base_dir, "MyDesigns.git")
            git_run(base_dir, "init", "--bare", origin_dir)
            # A URL, as users paste: forward slashes on every OS.
            origin = Path(origin_dir).as_uri()

            suggested = default_path_for_new_repo("", repos_dir, safe_base)
            validated = validate_repo_inputs(add_new, suggested, origin, add_new)["path"]
            name = derive_repo_name_from_url(origin)
            local_path = resolve_new_repo_path(name, validated, True, repos_dir, safe_base)
            if name != "MyDesigns":
                details.append(f"derived name {name!r}")
            if os.path.normcase(local_path) != os.path.normcase(os.path.join(repos_dir, "MyDesigns")):
                details.append(f"clone folder {local_path!r} does not follow the derived name")
            error = setup_new_repository(name, local_path, origin, git_run)
            if error:
                details.append(f"setup failed: {error}")
                return False
            if os.path.isdir(os.path.join(validated, ".git")):
                details.append("test premise broken: the suggested folder is a repo too")
            ui = _PipelineTestUI()
            result = self._push(local_path, [(self._write_export(base_dir, "model.step", "FIRST"), "model.step")], ui)
            if not result:
                details.append(f"first push failed: {ui.errors}")
            typed = os.path.join(base_dir, "Typed", "Folder")
            if resolve_new_repo_path("Other", typed, False, repos_dir, safe_base) != os.path.normpath(typed):
                details.append("a typed folder was not kept")
            # Wiring guard: the dialog must push from the folder it set up
            # (the full flow is covered in tests/unit/test_dialog.py).
            dialog_src = (Path(__file__).resolve().parent.parent / "src" / "push_dialog.py").read_text(
                encoding="utf-8"
            )
            if "normalized_repo_path = local_path" not in dialog_src:
                details.append("push_dialog.py no longer pushes from the set-up folder")
            return True

        self._run_pipeline_case("T_SETUP_01", "Setup: blank name uses the clone folder", body)

    def test_setup_origin_mismatch(self):
        """T_SETUP_02: an existing origin is only re-pointed after confirmation (audit REL-10)."""

        def body(base_dir, details):
            from dialog_helpers import setup_new_repository
            from fusion_git_core import git_run

            local = os.path.join(base_dir, "existing")
            git_run(base_dir, "init", local)
            with open(os.path.join(local, "keep.txt"), "w", encoding="utf-8") as fh:
                fh.write("existing project\n")
            git_run(local, "remote", "add", "origin", "https://example.invalid/old.git")

            def origin_url():
                return git_run(local, "remote", "get-url", "origin").stdout.strip()

            if not setup_new_repository("x", local, "https://example.invalid/new.git", git_run):
                details.append("re-pointing without a confirm callback should be refused")
            if origin_url() != "https://example.invalid/old.git":
                details.append("origin changed without confirmation")
            if not setup_new_repository("x", local, "https://example.invalid/new.git", git_run,
                                        confirm=lambda q: False):
                details.append("declining should refuse")
            if setup_new_repository("x", local, "https://example.invalid/new.git", git_run,
                                    confirm=lambda q: True) is not None:
                details.append("confirmed re-point failed")
            if origin_url() != "https://example.invalid/new.git":
                details.append("origin not updated after confirmation")
            return True

        self._run_pipeline_case("T_SETUP_02", "Setup: origin mismatch needs confirmation", body)

    @staticmethod
    def _import_release_scripts():
        scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import check_release
        import package

        return package, check_release

    def test_release_consistency(self):
        """T_RELEASE: manifest, VERSION, CHANGELOG, README and add-in ID agree (check_release)."""
        self.log_test_start("T_RELEASE", "release surfaces agree")
        try:
            _, check_release = self._import_release_scripts()
            problems = check_release.check()
            # A tag that differs from the manifest must be refused.
            version = check_release.manifest_version()
            if not any("does not match" in p for p in check_release.check(tag=f"v{version}")):
                problems.append("a v-prefixed tag was not refused")
            notes = check_release.changelog_section(version)
            if not notes or f"## {version}" in notes or "\n## " in notes:
                problems.append("release notes are empty or include other versions")
            self.record_result("T_RELEASE", "release surfaces agree", not problems, "; ".join(problems))
        except Exception as e:
            self.record_result("T_RELEASE", "release surfaces agree", False, str(e))

    def test_package_build_and_validation(self):
        """T_PACKAGE: the ZIP builds reproducibly, passes validation, and broken ZIPs fail it."""
        self.log_test_start("T_PACKAGE", "package build and validation")
        out = tempfile.mkdtemp(prefix="fusion_pkg_")
        try:
            import zipfile

            package, _ = self._import_release_scripts()
            problems = []

            first = package.build("HEAD", Path(out) / "a")
            second = package.build("HEAD", Path(out) / "b")
            if first.read_bytes() != second.read_bytes():
                problems.append("two builds of the same commit differ")
            errors = package.validate(first)
            if errors:
                problems.append(f"real package invalid: {errors}")

            with zipfile.ZipFile(first) as good:
                entries = {info.filename: good.read(info) for info in good.infolist()}
            prefix = f"{package.ADDIN_NAME}/"
            manifest_name = f"{prefix}{package.ADDIN_NAME}.manifest"
            manifest = json.loads(entries[manifest_name])
            names = set(entries)
            if f"{prefix}push_cli.py" in names or f"{prefix}diagnostic.py" in names:
                problems.append("developer tools are in the package")
            # Every add-in module in src/ is shipped, except the developer tools.
            src_dir = Path(__file__).resolve().parent.parent / "src"
            runtime_modules = {
                p.name for p in src_dir.glob("*.py")
                if f"src/{p.name}" not in package.EXCLUDED_FILES
            }
            unpackaged = sorted(m for m in runtime_modules if f"{prefix}{m}" not in names)
            if unpackaged:
                problems.append(f"modules missing from the package: {unpackaged}")

            def with_manifest(**changes):
                m = dict(manifest)
                for key, value in changes.items():
                    if value is None:
                        m.pop(key, None)
                    else:
                        m[key] = value
                return {**entries, manifest_name: json.dumps(m).encode()}

            broken_cases = {
                "missing module": {k: v for k, v in entries.items() if not k.endswith("dialog_helpers.py")},
                "syntax error": {**entries, f"{prefix}fusion_git_core.py": b"def broken(:\n"},
                "invalid GUID": with_manifest(id="not-a-guid"),
                "different GUID": with_manifest(id="00000000-0000-4000-8000-000000000000"),
                "bad version": with_manifest(version="banana"),
                "missing type": with_manifest(type=None),
                "extra file": {**entries, f"{prefix}push_cli.py": b"print('dev tool')\n"},
                "foreign import": {
                    **entries,
                    f"{prefix}dialog_helpers.py": entries[f"{prefix}dialog_helpers.py"] + b"\nimport requests\n",
                },
            }
            for label, files in broken_cases.items():
                path = Path(out) / f"broken-{label.replace(' ', '-')}.zip"
                with zipfile.ZipFile(path, "w") as z:
                    for name, data in files.items():
                        z.writestr(name, data)
                if not package.validate(path):
                    problems.append(f"broken package accepted: {label}")
            if not any("does not match" in e for e in package.validate(first, expect_version="9.9.9")):
                problems.append("wrong expected version accepted")

            self.record_result("T_PACKAGE", "package build and validation", not problems, "; ".join(problems))
        except Exception as e:
            self.record_result("T_PACKAGE", "package build and validation", False, str(e))
        finally:
            self._cleanup_dir(out)

    def test_display_name(self):
        """T_NAME: the user-visible name is "Push to GitHub"; the internal command id is frozen."""
        self.log_test_start("T_NAME", "Display name and frozen command id")
        root = Path(__file__).resolve().parent.parent
        problems = []
        main_src = (root / "src" / "Push_To_GitHub.py").read_text(encoding="utf-8")
        if 'CMD_NAME = "Push to GitHub"' not in main_src:
            problems.append("CMD_NAME is not 'Push to GitHub'")
        # Changing CMD_ID would reset users' toolbar placement; it is not shown to users.
        if 'CMD_ID = "PushToGitHub_Cmd_ZAC_V7_4"' not in main_src:
            problems.append("CMD_ID changed")
        for pattern in ("*.md", "*.py"):
            for path in root.rglob(pattern):
                if ".git" in path.parts or "__pycache__" in path.parts:
                    continue
                if "(ZAC)" in path.read_text(encoding="utf-8", errors="replace"):
                    problems.append(f"'(ZAC)' in {path.relative_to(root)}")
        # This file and the CHANGELOG (history) name the old label on purpose.
        problems = [p for p in problems if "test_runner.py" not in p and "CHANGELOG.md" not in p]
        self.record_result("T_NAME", "Display name and frozen command id", not problems, "; ".join(problems))

    def test_no_force_push_in_source(self):
        """T_NOFORCE: no force-push option or setting anywhere in the shipped code."""
        self.log_test_start("T_NOFORCE", "No force push in source")
        root = Path(__file__).resolve().parent.parent
        pattern = re.compile(r"--force|force-with-lease|force-if-includes|\bskip_pull\b|\"skipPull\"")
        hits = []
        for py in sorted((root / "src").glob("*.py")):
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{py.name}:{lineno}")
        # The old force-push setting may only appear in the settings store's
        # list of obsolete keys, which drops it when settings are loaded.
        import settings_store
        if "skipPullDefault" not in settings_store.OBSOLETE_PROFILE_KEYS:
            hits.append("settings_store no longer drops a saved skipPullDefault")
        if settings_store.migrate({"R": {"path": "x", "skipPullDefault": True}})["repositories"]["R"].get(
            "skipPullDefault"
        ) is not None:
            hits.append("a saved skipPullDefault survives migration")
        for py in sorted((root / "src").glob("*.py")):
            for line in py.read_text(encoding="utf-8").splitlines():
                if "skipPullDefault" in line and not line.strip().startswith("#") and not (
                    py.name == "settings_store.py" and "OBSOLETE_PROFILE_KEYS" in line
                ):
                    hits.append(f"skipPullDefault still read or written in {py.name}: {line.strip()}")
        self.record_result("T_NOFORCE", "No force push in source", not hits, "; ".join(hits))

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
            self.test_pipeline_busy_checkout_untouched()
            self.test_pipeline_new_repo_bootstrap()
            self.test_pipeline_cli_end_to_end()
            self.test_pipeline_branch_override_reuse()
            self.test_pipeline_template_branch_uniquify()
            self.test_pipeline_reused_branch_builds_on_remote_tip()
            self.test_pipeline_never_overwrites_remote()
            self.test_pipeline_single_history()
            self.test_pipeline_default_branch_override_warns()
            self.test_pipeline_timeout()
            self.test_pipeline_size_gate()
            self.test_pipeline_non_ascii()
            self.test_pipeline_history_bytes_preserved()
            self.test_pipeline_rejects_bad_paths_and_names()
            self.test_pipeline_token_requires_https()
            self.test_setup_blank_name_uses_clone_folder()
            self.test_setup_origin_mismatch()
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
        self.test_t_version_consistency()
        self.test_release_consistency()
        self.test_package_build_and_validation()
        self.test_t005_cli_harness_help()

    def run_core_module_tests(self):
        """Run core module tests"""
        print("\n=== Core Module Tests ===")
        self.test_core_git_functions()
        self.test_dialog_helpers_url_functions()
        self.test_credential_scoping()
        self.test_secret_redaction_and_urls()
        self.test_export_subfolder_helpers()
        self.test_no_force_push_in_source()
        self.test_display_name()

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


def _src_version() -> str:
    try:
        import fusion_git_core

        return fusion_git_core.VERSION
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="FusionToGitHub Test Runner")
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
    
    # Load src/ as the add-in package, as Fusion does (tests/addin_package.py);
    # src/ itself is never put on sys.path.
    sys.path.insert(0, str(script_dir))
    import addin_package

    addin_package.install()
    
    runner = TestRunner(verbose=args.verbose)
    
    print(f"FusionToGitHub - Automated Test Runner (src version {_src_version()})")
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