#!/usr/bin/env python3
"""Build and validate the installable Push_To_GitHub add-in ZIP.

    python scripts/package.py build [--ref HEAD] [--out dist] [--expect-version X.Y.Z]
    python scripts/package.py validate PATH.zip [--expect-version X.Y.Z]

The ZIP is built from the *committed* tree at --ref, never from the working
tree, with fixed timestamps, permissions and ordering. Building the same
commit twice gives a byte-identical file on the same machine.

Users unzip it into Fusion's AddIns folder, which gives
``AddIns/Push_To_GitHub/Push_To_GitHub.manifest``. The same file is the
GitHub release asset the Community Store installs.

Standard library only; no third-party packages.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

ADDIN_NAME = "Push_To_GitHub"
# Frozen add-in ID (maintainer decision Q10). The Community Store and Fusion
# use it to recognise the add-in across versions; never change it.
ADDIN_ID = "a9902311-5949-4d34-9ea6-3d4e6250d4a9"

# Files shipped to end users: path in the repo -> path inside the add-in folder.
PACKAGE_FILES: Dict[str, str] = {
    "src/Push_To_GitHub.manifest": "Push_To_GitHub.manifest",
    "src/Push_To_GitHub.py": "Push_To_GitHub.py",
    "src/fusion_git_core.py": "fusion_git_core.py",
    "src/dialog_helpers.py": "dialog_helpers.py",
    "src/addin_logging.py": "addin_logging.py",
    "src/credentials.py": "credentials.py",
    "src/fusion_export.py": "fusion_export.py",
    "src/push_controller.py": "push_controller.py",
    "src/push_dialog.py": "push_dialog.py",
    "src/settings_store.py": "settings_store.py",
    "src/AddInIcon.svg": "AddInIcon.svg",
    "LICENSE": "LICENSE",
}
# Developer tools kept in the repo but never shipped (maintainer decision Q12).
EXCLUDED_FILES = ("src/push_cli.py", "src/diagnostic.py")

REQUIRED_MANIFEST_KEYS = (
    "autodeskProduct",
    "type",
    "id",
    "author",
    "description",
    "version",
    "runOnStartup",
    "supportedOS",
)
ALLOWED_SUPPORTED_OS = {"windows", "mac", "windows|mac", "mac|windows"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_MANIFEST_BYTES = 32 * 1024  # Community Store limit

FILE_MODE = 0o100644
DIR_MODE = 0o040755


def asset_name(version: str) -> str:
    return f"{ADDIN_NAME}-{version}.zip"


def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr.decode(errors='replace')}")
    return proc.stdout


def _zip_time(epoch_seconds: int):
    # ZIP timestamps cannot be earlier than 1980.
    t = time.gmtime(max(epoch_seconds, 315532800))
    return (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)


def build(ref: str = "HEAD", out_dir: Path = ROOT / "dist") -> Path:
    """Build the ZIP from commit *ref* and write it plus a .sha256 file to *out_dir*."""
    sha = _git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    commit_time = int(_git("show", "-s", "--format=%ct", sha).decode().strip())
    date_time = _zip_time(commit_time)

    contents = {arc: _git("cat-file", "blob", f"{sha}:{src}") for src, arc in PACKAGE_FILES.items()}
    manifest = json.loads(contents["Push_To_GitHub.manifest"].decode("utf-8"))
    version = str(manifest.get("version", ""))
    if not VERSION_RE.match(version):
        raise SystemExit(f"Manifest version {version!r} is not X.Y.Z")

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / asset_name(version)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.comment = f"{ADDIN_NAME} {version} {sha}".encode("ascii")
        folder = zipfile.ZipInfo(f"{ADDIN_NAME}/", date_time)
        folder.create_system = 3
        folder.external_attr = (DIR_MODE << 16) | 0x10
        archive.writestr(folder, b"")
        for arc in sorted(contents):
            info = zipfile.ZipInfo(f"{ADDIN_NAME}/{arc}", date_time)
            info.create_system = 3  # same header on every OS
            info.external_attr = FILE_MODE << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, contents[arc], compresslevel=9)
    zip_path.write_bytes(buffer.getvalue())

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / f"{zip_path.name}.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    return zip_path


def _stdlib_modules() -> set:
    names = set(getattr(sys, "stdlib_module_names", ()))
    names.update(sys.builtin_module_names)
    return names


def validate(zip_path: Path, expect_version: Optional[str] = None) -> List[str]:
    """Return a list of problems with the package; empty means it is valid."""
    errors: List[str] = []
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"not a readable ZIP: {exc}"]

    with archive:
        bad = archive.testzip()
        if bad is not None:
            errors.append(f"corrupt entry: {bad}")

        names = archive.namelist()
        if len(names) != len(set(names)):
            errors.append("duplicate entries")
        for name in names:
            if name.startswith("/") or "\\" in name or ".." in name.split("/"):
                errors.append(f"unsafe path: {name}")
            if not name.startswith(f"{ADDIN_NAME}/"):
                errors.append(f"entry outside the {ADDIN_NAME}/ folder: {name}")

        expected = {f"{ADDIN_NAME}/"} | {f"{ADDIN_NAME}/{arc}" for arc in PACKAGE_FILES.values()}
        missing = expected - set(names)
        extra = set(names) - expected
        if missing:
            errors.append(f"missing files: {sorted(missing)}")
        if extra:
            errors.append(f"unexpected files: {sorted(extra)}")

        def read(arc: str) -> Optional[bytes]:
            try:
                return archive.read(f"{ADDIN_NAME}/{arc}")
            except KeyError:
                return None

        # Manifest
        manifest_bytes = read(f"{ADDIN_NAME}.manifest")
        manifest: dict = {}
        if manifest_bytes is not None:
            if len(manifest_bytes) > MAX_MANIFEST_BYTES:
                errors.append("manifest is larger than 32 KiB")
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"manifest is not valid JSON: {exc}")
        if not isinstance(manifest, dict):
            errors.append("manifest must be a JSON object")
            manifest = {}
        for key in REQUIRED_MANIFEST_KEYS:
            if key not in manifest:
                errors.append(f"manifest is missing '{key}'")
        if manifest:
            if manifest.get("type") != "addin":
                errors.append(f"manifest type is {manifest.get('type')!r}, expected 'addin'")
            if manifest.get("autodeskProduct") != "Fusion":
                errors.append(f"manifest autodeskProduct is {manifest.get('autodeskProduct')!r}")
            if manifest.get("supportedOS") not in ALLOWED_SUPPORTED_OS:
                errors.append(f"manifest supportedOS {manifest.get('supportedOS')!r} not allowed")
            addin_id = str(manifest.get("id", ""))
            try:
                if str(uuid.UUID(addin_id)) != addin_id.lower():
                    errors.append(f"manifest id {addin_id!r} is not a canonical UUID")
            except ValueError:
                errors.append(f"manifest id {addin_id!r} is not a UUID")
            if addin_id.lower() != ADDIN_ID:
                errors.append(f"manifest id {addin_id!r} is not the frozen add-in ID {ADDIN_ID}")
            version = str(manifest.get("version", ""))
            if not VERSION_RE.match(version):
                errors.append(f"manifest version {version!r} is not X.Y.Z")
            elif expect_version is not None and version != expect_version:
                errors.append(f"manifest version {version} does not match expected {expect_version}")
            icon = manifest.get("iconFilename")
            if icon and read(str(icon)) is None:
                errors.append(f"manifest icon {icon!r} is not in the package")

        # Python modules: must compile and import only what exists in Fusion.
        packaged_modules = {Path(arc).stem for arc in PACKAGE_FILES.values() if arc.endswith(".py")}
        allowed_roots = _stdlib_modules() | packaged_modules | {"adsk"}
        for arc in sorted(a for a in PACKAGE_FILES.values() if a.endswith(".py")):
            source = read(arc)
            if source is None:
                continue
            try:
                tree = ast.parse(source.decode("utf-8"), filename=arc)
                compile(tree, arc, "exec")
            except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
                errors.append(f"{arc} does not compile: {exc}")
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        relative_modules = (
                            [node.module] if node.module else [alias.name for alias in node.names]
                        )
                        for module in relative_modules:
                            if node.level != 1 or module not in packaged_modules:
                                errors.append(
                                    f"{arc} imports {'.' * node.level + module!r}, "
                                    "which is not in the package"
                                )
                    elif node.module:
                        modules = [node.module]
                for module in modules:
                    root = module.split(".")[0]
                    if root not in allowed_roots:
                        errors.append(f"{arc} imports {module!r}, which is not in the package")

    # The Community Store rule "folder == manifest stem == script stem" is
    # covered by the exact file-set check above.
    return errors


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build the ZIP from a commit, then validate it")
    b.add_argument("--ref", default="HEAD", help="commit to package (default: HEAD)")
    b.add_argument("--out", default=str(ROOT / "dist"), help="output folder (default: dist)")
    b.add_argument("--expect-version", help="fail unless the manifest has this version")
    v = sub.add_parser("validate", help="validate an existing ZIP")
    v.add_argument("zip", help="path to the ZIP")
    v.add_argument("--expect-version", help="fail unless the manifest has this version")
    args = parser.parse_args(argv)

    if args.command == "build":
        zip_path = build(args.ref, Path(args.out))
    else:
        zip_path = Path(args.zip)
    problems = validate(zip_path, args.expect_version)
    if problems:
        print(f"{zip_path}: INVALID", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"{zip_path}: OK ({zip_path.stat().st_size} bytes, sha256 {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
