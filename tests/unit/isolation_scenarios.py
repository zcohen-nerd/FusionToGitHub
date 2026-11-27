"""Same-process load scenarios for the add-in (risk R-25), one per run.

Run by test_package_isolation.py in a fresh, isolated interpreter
(``python -I -B isolation_scenarios.py <scenario> <workdir>``) so that
nothing in ``sys.modules`` leaks between scenarios. Prints one JSON object.

Fusion is emulated as the add-in template implies: each add-in folder is
loaded as a package named after the folder, and its main file is imported
inside it. "Run again after an update" is a fresh import of the main file
(as Fusion does: DiegoV71's report shows the new main file ran), with the
package's other modules still in ``sys.modules`` from before. The simulated
Fusion API (tests/fakes) stands in for adsk.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))

import adsk  # noqa: E402
import adsk.core  # noqa: E402

ENTRY = "Push_To_GitHub"


def runtime_files():
    spec = importlib.util.spec_from_file_location("_pkg_script", os.path.join(ROOT, "scripts", "package.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return dict(script.PACKAGE_FILES)


def install(folder, version=None, marker=None):
    """Copy the add-in into *folder* (an update replaces the files).

    *version* fakes its VERSION; *marker* is appended to every module as
    ``S4_TEST_MARKER`` so a test can tell which copy of each module runs.
    """
    os.makedirs(folder, exist_ok=True)
    for src, arc in runtime_files().items():
        shutil.copyfile(os.path.join(ROOT, src), os.path.join(folder, arc))
        if marker and arc.endswith(".py"):
            with open(os.path.join(folder, arc), "a", encoding="utf-8") as fh:
                fh.write(f'\nS4_TEST_MARKER = "{marker}"\n')
    if version:
        core = os.path.join(folder, "fusion_git_core.py")
        with open(core, encoding="utf-8") as fh:
            text = fh.read()
        text, n = re.subn(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', text, count=1, flags=re.M)
        assert n == 1, "VERSION line not found"
        with open(core, "w", encoding="utf-8") as fh:
            fh.write(text)
    return folder


def fusion_load(folder):
    """Load (or re-run) the add-in in *folder* the way Fusion does."""
    package = os.path.basename(folder)
    if package not in sys.modules:
        spec = importlib.machinery.ModuleSpec(package, None, is_package=True)
        spec.submodule_search_locations = [folder]
        sys.modules[package] = importlib.util.module_from_spec(spec)
    sys.modules.pop(f"{package}.{ENTRY}", None)  # Fusion runs the main file afresh
    return importlib.import_module(f"{package}.{ENTRY}")


def buttons(ui):
    found = 0
    for i in range(ui.allToolbarPanels.count):
        if ui.allToolbarPanels.item(i).controls.itemById("PushToGitHub_Cmd_ZAC_V7_4_Control"):
            found += 1
    return found


def plant_bare_modules(work):
    """Modules of an older add-in version loaded under bare names (DiegoV71's reproduction)."""
    old = os.path.join(work, "old_bare")
    os.makedirs(old)
    with open(os.path.join(old, "fusion_git_core.py"), "w", encoding="utf-8") as fh:
        fh.write('VERSION = "0.3.3"\n\ndef redact_secrets(text, secrets=()):\n    return text\n')
    with open(os.path.join(old, "dialog_helpers.py"), "w", encoding="utf-8") as fh:
        fh.write("OLD = True\n")
    sys.path.insert(0, old)
    planted = {name: importlib.import_module(name) for name in ("fusion_git_core", "dialog_helpers")}
    sys.path.remove(old)
    return planted


def scenario_stale_bare_names(work):
    planted = plant_bare_modules(work)
    # Control: the pre-0.6.0 style bare import fails exactly as reported.
    try:
        exec("from fusion_git_core import push_export", {})
        control = "no error"
    except ImportError as exc:
        control = str(exc)
    entry = fusion_load(install(os.path.join(work, "Push_To_GitHub")))
    entry.run(None)
    package = entry.__package__
    return {
        "control": control,
        "version": entry.VERSION,
        "has_push_export": hasattr(sys.modules[f"{package}.fusion_git_core"], "push_export"),
        "bare_untouched": all(sys.modules[n] is m for n, m in planted.items()),
        "buttons": buttons(entry.ui),
    }


def open_dialog(entry):
    """Open the dialog as a click on the button would (loads push_dialog and friends)."""
    entry.credential_store = importlib.import_module(f"{entry.__package__}.credentials").MemoryCredentialStore()
    entry.ui.open_command(entry.CMD_ID)


def modules_in_use(entry):
    """Marker of every add-in module reachable the way the add-in reaches it.

    ``from . import x`` reads the package's attribute ``x`` before
    sys.modules, so both are checked, along with the entry module's globals.
    """
    package = sys.modules[entry.__package__]
    seen = {}
    for name in sorted(runtime_names() - {ENTRY}):
        for where, module in (("sys.modules", sys.modules.get(f"{entry.__package__}.{name}")),
                              ("package attribute", vars(package).get(name)),
                              ("entry global", vars(entry).get(name))):
            if module is not None:
                seen[f"{name} ({where})"] = vars(module).get("S4_TEST_MARKER")
    bridge = vars(entry).get("bridge")
    if bridge is not None:
        # The globals of the module the running bridge's class came from.
        seen["bridge class"] = type(bridge).start.__globals__.get("S4_TEST_MARKER")
    return seen


def scenario_update_and_rollback(work, first, second):
    folder = os.path.join(work, "Push_To_GitHub")
    entry = fusion_load(install(folder, version=first, marker="before"))
    entry.run(None)
    open_dialog(entry)  # the old version's dialog modules are now loaded too
    entry.stop(None)
    core_before = sys.modules[f"{entry.__package__}.fusion_git_core"]
    install(folder, version=second, marker="after")  # the Store (or the user) replaces the files
    # Control: the old module is still loaded under the package's name.
    stale_before_rerun = importlib.import_module(f"{entry.__package__}.fusion_git_core").VERSION
    entry = fusion_load(folder)
    entry.run(None)
    open_dialog(entry)
    core_after = sys.modules[f"{entry.__package__}.fusion_git_core"]
    in_use = modules_in_use(entry)
    return {
        "stale_modules_in_use": sorted(k for k, v in in_use.items() if v != "after"),
        "modules_checked": len(in_use),
        "stale_before_rerun": stale_before_rerun,
        "entry_version": entry.VERSION,
        "core_version": core_after.VERSION,
        "core_replaced": core_after is not core_before,
        "buttons": buttons(entry.ui),
        "events": list(adsk.core.Application.get().registered_custom_events),
    }


def scenario_two_versions(work):
    other_addin = types.ModuleType("OtherAddin.fusion_git_core")  # unrelated add-in, same module name
    sys.modules["OtherAddin.fusion_git_core"] = other_addin
    first = fusion_load(install(os.path.join(work, "Push_To_GitHub")))
    second = fusion_load(install(os.path.join(work, "Push_To_GitHub_copy"), version="9.9.9"))
    first.run(None)
    second.run(None)
    ui = first.ui
    result = {
        "versions": [first.VERSION, second.VERSION],
        "cores": [sys.modules["Push_To_GitHub.fusion_git_core"].VERSION,
                  sys.modules["Push_To_GitHub_copy.fusion_git_core"].VERSION],
        "buttons": buttons(ui),
        "second_owns": second.owns_command,
        "warning": any("Another copy" in text for text in ui.texts()),
        "unrelated_untouched": sys.modules.get("OtherAddin.fusion_git_core") is other_addin,
    }
    second.stop(None)
    result["buttons_after_second_stop"] = buttons(ui)
    first.stop(None)
    result["buttons_after_both_stop"] = buttons(ui)
    return result


def scenario_same_package_other_folder(work):
    first = install(os.path.join(work, "a", "Push_To_GitHub"))
    second = install(os.path.join(work, "b", "Push_To_GitHub"))
    fusion_load(first)
    # A second folder with the same name, loaded into the same package name.
    sys.modules["Push_To_GitHub"].__path__[:] = [second]
    try:
        fusion_load(second)
        return {"error": None}
    except ImportError as exc:
        return {"error": str(exc)}


def scenario_not_a_package(work):
    folder = install(os.path.join(work, "Push_To_GitHub"))
    spec = importlib.util.spec_from_file_location("Push_To_GitHub_script", os.path.join(folder, "Push_To_GitHub.py"))
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return {"error": None}
    except ImportError as exc:
        return {"error": str(exc), "bare_names": [n for n in ("fusion_git_core", "push_dialog") if n in sys.modules]}


def scenario_restarts(work):
    folder = install(os.path.join(work, "Push_To_GitHub"))
    counts = []
    for _ in range(3):
        entry = fusion_load(folder)
        entry.run(None)
        entry.run(None)
        counts.append([buttons(entry.ui), len(adsk.core.Application.get().registered_custom_events)])
        entry.stop(None)
    counts.append([buttons(entry.ui), len(adsk.core.Application.get().registered_custom_events)])
    # A bare-named *module* of the add-in (the package itself is named after
    # the folder, which here happens to equal the main file's name).
    leaked = sorted(n for n in runtime_names() if n in sys.modules and not hasattr(sys.modules[n], "__path__"))
    return {"counts": counts, "bare_names_registered": leaked}


def install_release(folder, tag):
    """Put a *released* version's add-in files (from its git tag) into *folder*."""
    import subprocess

    os.makedirs(folder, exist_ok=True)
    names = subprocess.run(["git", "-C", ROOT, "ls-tree", "--name-only", f"{tag}:src"],
                           capture_output=True, text=True, check=True).stdout.split()
    for name in names:
        if name.endswith((".py", ".manifest", ".svg")):
            data = subprocess.run(["git", "-C", ROOT, "show", f"{tag}:src/{name}"], capture_output=True, check=True).stdout
            with open(os.path.join(folder, name), "wb") as fh:
                fh.write(data)
    return folder


def scenario_real_release(work, *versions):
    """Run, Stop, replace the files, Run again... through *versions*, in one process.

    Each version is a release tag (its real files) or "current" (this tree).
    A failure to load or start is recorded, as Fusion would report a failed
    start, instead of ending the scenario.
    """
    folder = os.path.join(work, "Push_To_GitHub")
    seen = []
    for version in versions:
        if version == "current":
            install(folder)
        else:
            install_release(folder, version)
        try:
            entry = fusion_load(folder)
            entry.run(None)
        except Exception as exc:  # a failed start, like the one reported in issue #11
            seen.append({"label": version, "error": f"{type(exc).__name__}: {exc}"})
            continue
        seen.append({"label": version, "version": entry.VERSION, "buttons": buttons(entry.ui)})
        entry.stop(None)
    return {"steps": seen}


def runtime_names():
    return {os.path.splitext(arc)[0] for arc in runtime_files().values() if arc.endswith(".py")}


SCENARIOS = {
    "stale_bare_names": scenario_stale_bare_names,
    "upgrade": lambda work: scenario_update_and_rollback(work, "0.5.0", None),
    "downgrade": lambda work: scenario_update_and_rollback(work, None, "0.4.0"),
    "two_versions": scenario_two_versions,
    "same_package_other_folder": scenario_same_package_other_folder,
    "not_a_package": scenario_not_a_package,
    "restarts": scenario_restarts,
    "real_release": scenario_real_release,
}

if __name__ == "__main__":
    name, workdir, *extra = sys.argv[1:]
    print("RESULT " + json.dumps(SCENARIOS[name](workdir, *extra)))
