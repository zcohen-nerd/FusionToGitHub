"""Package isolation and same-process updates (risk R-25, issue #11, reported by DiegoV71).

Each scenario runs in a fresh, isolated interpreter (see isolation_scenarios.py)
against copies of the add-in folder, with the SIMULATED Fusion API. What
real Fusion does on Stop/Run and on a Community Store update is checked by
the manual checklist (section K).
"""

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

import _paths

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENARIOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isolation_scenarios.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import package  # noqa: E402

sys.path.remove(os.path.join(ROOT, "scripts"))

import fusion_git_core  # noqa: E402

CURRENT = fusion_git_core.VERSION


def run_scenario(name, *extra):
    work = tempfile.mkdtemp(prefix="ftg_iso_")
    try:
        home = os.path.join(work, "home")
        os.makedirs(home)
        env = dict(os.environ, HOME=home, USERPROFILE=home)
        proc = subprocess.run(
            [sys.executable, "-I", "-B", SCENARIOS, name, work, *extra],
            capture_output=True, text=True, timeout=120, env=env, cwd=work,
        )
    finally:
        _paths.force_rmtree(work)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    if proc.returncode != 0 or not lines:
        raise AssertionError(f"scenario {name} failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(lines[-1][len("RESULT "):])


class SameProcessLoadTests(unittest.TestCase):
    def test_modules_of_an_older_version_under_bare_names_are_not_used(self):
        # DiegoV71's reproduction: 0.3.3's fusion_git_core and dialog_helpers
        # already loaded under their bare names.
        result = run_scenario("stale_bare_names")
        self.assertIn("cannot import name 'push_export'", result["control"])  # the reported failure
        self.assertEqual(result["version"], CURRENT)
        self.assertTrue(result["has_push_export"])
        self.assertTrue(result["bare_untouched"], "another add-in's (or version's) modules were unloaded")
        self.assertEqual(result["buttons"], 1)

    def test_stop_update_run_loads_the_new_version(self):
        result = run_scenario("upgrade")
        self.assertEqual(result["stale_before_rerun"], "0.5.0")  # control: the old module was still loaded
        self.assertEqual(result["entry_version"], CURRENT)
        self.assertEqual(result["core_version"], CURRENT)
        self.assertTrue(result["core_replaced"])
        self.assertEqual(result["buttons"], 1)
        self.assertEqual(result["events"], ["PushToGitHub_Cmd_ZAC_V7_4_PushWorker"])

    def test_rollback_to_an_earlier_version_in_the_same_session(self):
        result = run_scenario("downgrade")
        self.assertEqual(result["stale_before_rerun"], CURRENT)
        self.assertEqual(result["entry_version"], "0.4.0")
        self.assertEqual(result["core_version"], "0.4.0")
        self.assertEqual(result["buttons"], 1)

    def test_two_installed_versions_keep_their_own_modules(self):
        result = run_scenario("two_versions")
        self.assertEqual(result["versions"], [CURRENT, "9.9.9"])
        self.assertEqual(result["cores"], [CURRENT, "9.9.9"])
        self.assertEqual(result["buttons"], 1)
        self.assertFalse(result["second_owns"])
        self.assertTrue(result["warning"])
        self.assertTrue(result["unrelated_untouched"])
        self.assertEqual(result["buttons_after_second_stop"], 1)  # the duplicate leaves the first copy alone
        self.assertEqual(result["buttons_after_both_stop"], 0)

    def test_a_same_named_package_from_another_folder_is_refused_not_mixed(self):
        result = run_scenario("same_package_other_folder")
        self.assertIsNotNone(result["error"])
        self.assertIn("Remove the duplicate add-in folder", result["error"])

    def test_the_entry_point_requires_a_package(self):
        result = run_scenario("not_a_package")
        self.assertIn("must be loaded by Fusion as a package", result["error"] or "")
        self.assertEqual(result["bare_names"], [])

    def test_repeated_run_stop_and_reload_keep_one_button_and_one_event(self):
        result = run_scenario("restarts")
        self.assertEqual(result["counts"], [[1, 1], [1, 1], [1, 1], [0, 0]])
        self.assertEqual(result["bare_names_registered"], [])


def _have_tags(*tags):
    for tag in tags:
        proc = subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],
                              capture_output=True)
        if proc.returncode != 0:
            if os.environ.get("CI"):
                raise AssertionError(f"release tag {tag} missing; CI must check out tags (fetch-depth: 0)")
            return False
    return True


@unittest.skipUnless(_have_tags("0.3.3", "0.4.0"), "release tags not available in this clone")
class RealReleaseTests(unittest.TestCase):
    """The *released* add-in files, from their git tags, in one Python process."""

    def test_control_the_reported_failure_from_0_3_3_to_0_4_0_is_reproduced(self):
        steps = run_scenario("real_release", "0.3.3", "0.4.0")["steps"]
        self.assertEqual(steps[0], {"label": "0.3.3", "version": "0.3.3", "buttons": 1})
        self.assertIn("cannot import name 'push_export' from 'fusion_git_core'", steps[1].get("error", ""))

    def test_updates_and_rollbacks_between_releases_and_this_version(self):
        steps = run_scenario("real_release", "0.3.3", "current", "0.4.0", "current", "0.3.3")["steps"]
        self.assertEqual(
            [(s["label"], s.get("version"), s.get("buttons"), s.get("error")) for s in steps],
            [("0.3.3", "0.3.3", 1, None), ("current", CURRENT, 1, None), ("0.4.0", "0.4.0", 1, None),
             ("current", CURRENT, 1, None), ("0.3.3", "0.3.3", 1, None)],
        )


class SourceRuleTests(unittest.TestCase):
    """The import rules the scenarios depend on, checked on the source."""

    def shipped_modules(self):
        return {os.path.splitext(arc)[0]: os.path.join(ROOT, src)
                for src, arc in package.PACKAGE_FILES.items() if arc.endswith(".py")}

    def test_shipped_modules_import_each_other_only_relatively(self):
        modules = self.shipped_modules()
        for name, path in modules.items():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    bare = [a.name for a in node.names if a.name.split(".")[0] in modules]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    bare = [node.module] if (node.module or "").split(".")[0] in modules else []
                else:
                    continue
                self.assertEqual(bare, [], f"{name}.py:{node.lineno} imports a sibling by bare name")

    def test_no_shipped_module_changes_sys_path(self):
        for name, path in self.shipped_modules().items():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                # sys.path.<anything>(...), sys.path = ..., sys.path[...] = ...
                target = node.func.value if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else None
                if isinstance(node, (ast.Assign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    target = next((t.value if isinstance(t, ast.Subscript) else t for t in targets), None)
                is_sys_path = (isinstance(target, ast.Attribute) and target.attr == "path"
                               and isinstance(target.value, ast.Name) and target.value.id == "sys")
                self.assertFalse(is_sys_path, f"{name}.py:{getattr(node, 'lineno', '?')} changes sys.path")

    def test_the_standalone_core_has_no_sibling_imports(self):
        # push_cli.py and diagnostic.py import fusion_git_core as a plain module.
        with open(os.path.join(ROOT, "src", "fusion_git_core.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        relative = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
        self.assertEqual(relative, [])

    def test_the_package_check_rejects_a_bare_sibling_import(self):
        def build(replace=None):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(f"{package.ADDIN_NAME}/", b"")
                for src, arc in package.PACKAGE_FILES.items():
                    with open(os.path.join(ROOT, src), "rb") as fh:
                        data = fh.read()
                    if replace and arc == replace[0]:
                        data = data.replace(replace[1], replace[2])
                    archive.writestr(f"{package.ADDIN_NAME}/{arc}", data)
            path = os.path.join(self.dir, "addin.zip")
            with open(path, "wb") as fh:
                fh.write(buffer.getvalue())
            return path

        self.dir = tempfile.mkdtemp(prefix="ftg_pkgcheck_")
        self.addCleanup(_paths.force_rmtree, self.dir)
        self.assertEqual(package.validate(build()), [])
        bad = build(("dialog_helpers.py", b"from .fusion_git_core import", b"from fusion_git_core import"))
        problems = package.validate(bad)
        self.assertTrue(any("by its bare name" in p and "dialog_helpers.py" in p for p in problems), problems)


class StandaloneTests(unittest.TestCase):
    def run_isolated(self, *args):
        # -E -s: no PYTHON* variables and no user site-packages, so only the
        # script's own folder is on sys.path (how a developer runs these
        # tools). UTF-8 output; a temporary home so no real log is read.
        home = tempfile.mkdtemp(prefix="ftg_home_")
        self.addCleanup(_paths.force_rmtree, home)
        env = dict(os.environ, HOME=home, USERPROFILE=home)
        return subprocess.run([sys.executable, "-E", "-s", "-X", "utf8", *args], capture_output=True,
                              encoding="utf-8", errors="replace", timeout=120, cwd=home, env=env)

    def test_push_cli_runs_as_a_plain_script(self):
        proc = self.run_isolated(os.path.join(ROOT, "src", "push_cli.py"), "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage", proc.stdout.lower())

    def test_diagnostic_imports_the_core_as_a_plain_script(self):
        proc = self.run_isolated(os.path.join(ROOT, "src", "diagnostic.py"))
        self.assertIn("fusion_git_core imported successfully", proc.stdout, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
