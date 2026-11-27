"""Load src/ the way Fusion loads the add-in: as a package.

The add-in's modules import each other relatively (``from . import x``), so
they only work inside a package (risk R-25). The tests load ``src/`` as the
package ``PACKAGE`` -- deliberately *not* the add-in's folder name, which
proves no code depends on that name -- with the simulated Fusion API
(``tests/fakes``) on ``sys.path``.

For convenience each runtime module is then also registered under its bare
name, so tests can keep writing ``import push_dialog`` and
``mock.patch("push_dialog.x")``; both names refer to the same module object.
These aliases exist only in the test process. The add-in itself never
registers bare names, and ``src/`` is never put on ``sys.path``.

The entry module is imported first, as in Fusion, because importing it
forgets the package's previously loaded modules.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FAKES = os.path.join(ROOT, "tests", "fakes")
PACKAGE = "ftg_addin_under_test"
ENTRY = "Push_To_GitHub"


def runtime_modules() -> List[str]:
    """The shipped Python modules, from ``scripts/package.py`` (the one list)."""
    spec = importlib.util.spec_from_file_location("_ftg_package_script", os.path.join(ROOT, "scripts", "package.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return sorted(
        os.path.splitext(arc)[0] for arc in script.PACKAGE_FILES.values() if arc.endswith(".py")
    )


def install(package: str = PACKAGE) -> object:
    """Load src/ as *package* (once per process) and alias its modules' bare names."""
    if package in sys.modules:
        return sys.modules[package]
    if FAKES not in sys.path:
        sys.path.insert(0, FAKES)
    spec = importlib.machinery.ModuleSpec(package, None, is_package=True)
    spec.submodule_search_locations = [SRC]
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[package] = pkg
    importlib.import_module(f"{package}.{ENTRY}")
    for name in runtime_modules():
        module = importlib.import_module(f"{package}.{name}")
        existing = sys.modules.setdefault(name, module)
        if existing is not module:
            raise RuntimeError(f"A module named {name!r} was imported before the add-in package was installed")
    return pkg


__all__ = ["ENTRY", "FAKES", "PACKAGE", "ROOT", "SRC", "install", "runtime_modules"]
