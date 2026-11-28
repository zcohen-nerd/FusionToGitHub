"""SIMULATED adsk.fusion: a design, its components and its export manager.

Nothing here is Fusion. ``ExportManager.execute`` writes a small file that
*looks like* the requested format (a ZIP for .f3d, an ISO-10303-21 header
for STEP, a complete binary STL, an IGES start record, text for SAT), so the
add-in's file checks can be exercised. Real Fusion writes the actual CAD
data. See tests/fakes/README.md for every assumption these fakes make.

Failure injection: ``ExportManager.failures[fmt]`` is one of ``"raise"``,
``"false"`` (execute returns False), ``"empty"`` (an empty file),
``"missing"`` (returns True but writes nothing) or ``"corrupt"`` (a file
without the format's signature). ``fail_formats`` (older tests) is the
same as ``"false"``.
"""

import struct
import zipfile


class MeshRefinementSettings:
    MeshRefinementHigh = 0
    MeshRefinementMedium = 1
    MeshRefinementLow = 2


class DistanceUnits:
    MillimeterDistanceUnits = 0
    CentimeterDistanceUnits = 1
    MeterDistanceUnits = 2
    InchDistanceUnits = 3
    FootDistanceUnits = 4


class Collection:
    """Fusion-style collection: ``count``, ``item(i)``, and iteration."""

    def __init__(self, items=()):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class BRepBody:
    def __init__(self, name="Body1", is_visible=True, assembly_context=None):
        self.name = name
        self.isVisible = is_visible
        self.assemblyContext = assembly_context  # None for a native body

    def createForAssemblyContext(self, occurrence):  # noqa: N802
        return BRepBody(self.name, self.isVisible and occurrence.isVisible, occurrence)


class Component:
    def __init__(self, name, bodies=None):
        self.name = name
        self._bodies = [BRepBody(b) if isinstance(b, str) else b for b in (bodies or [])]
        self._occurrences = []

    @property
    def bRepBodies(self):  # noqa: N802
        return Collection(self._bodies)

    @property
    def occurrences(self):
        return Collection(self._occurrences)

    @property
    def allOccurrences(self):  # noqa: N802
        """Every occurrence below this component, depth first (as Fusion lists them)."""
        found = []

        def walk(occurrences):
            for occurrence in occurrences:
                found.append(occurrence)
                walk(occurrence.childOccurrences)

        walk(self._occurrences)
        return Collection(found)

    def add_occurrence(self, component, linked=False, broken=False, visible=True):
        """Insert *component* here (test helper; Fusion uses ``occurrences.addNewComponent``)."""
        occurrence = Occurrence(component, None, self._occurrences, linked=linked, broken=broken, visible=visible)
        self._occurrences.append(occurrence)
        return occurrence


class Occurrence:
    def __init__(self, component, parent, siblings, linked=False, broken=False, visible=True):
        self.component = component
        self._parent = parent
        self._linked = linked
        self._broken = broken  # simulates a reference Fusion can't resolve
        self.isVisible = visible
        self._children = []
        self._index = 1 + sum(1 for s in siblings if s.component is component)
        self.name = f"{component.name}:{self._index}"

    @property
    def isReferencedComponent(self):  # noqa: N802
        if self._broken:
            raise RuntimeError("InternalValidationError : reference could not be resolved")
        return self._linked

    @property
    def fullPathName(self):  # noqa: N802
        return f"{self._parent.fullPathName}+{self.name}" if self._parent else self.name

    @property
    def childOccurrences(self):  # noqa: N802
        return Collection(self._children)

    @property
    def bRepBodies(self):  # noqa: N802
        # Fusion returns proxies of the component's bodies in this
        # occurrence's assembly context.
        return Collection(body.createForAssemblyContext(self) for body in self.component._bodies)

    def add_occurrence(self, component, linked=False, broken=False, visible=True):
        """Insert *component* inside this occurrence's component (test helper)."""
        occurrence = Occurrence(component, self, self._children, linked=linked or self._linked, broken=broken,
                                visible=visible and self.isVisible)
        self._children.append(occurrence)
        return occurrence


class ExportOptions:
    def __init__(self, fmt, path, geometry=None):
        self.format = fmt
        self.filename = path
        self.geometry = geometry


class STEPExportOptions(ExportOptions):
    def __init__(self, path, geometry=None):
        super().__init__("step", path, geometry)
        self.applicationProtocol = "AP214"


class STLExportOptions(ExportOptions):
    """``unitType`` exists in newer Fusion builds only (see LegacySTLExportOptions)."""

    def __init__(self, path, geometry=None):
        super().__init__("stl", path, geometry)
        self.meshRefinement = MeshRefinementSettings.MeshRefinementHigh
        self.isBinaryFormat = True
        self.isOneFilePerBody = False
        self.unitType = DistanceUnits.CentimeterDistanceUnits  # Fusion's internal unit


class LegacySTLExportOptions(ExportOptions):
    """STL options of a Fusion version without ``unitType``."""

    def __init__(self, path, geometry=None):
        super().__init__("stl", path, geometry)
        self.meshRefinement = MeshRefinementSettings.MeshRefinementHigh
        self.isBinaryFormat = True
        self.isOneFilePerBody = False


def _content(fmt, label):
    """Bytes that pass the add-in's basic signature check for *fmt*."""
    text = f"simulated {fmt} export of {label}"
    if fmt == "f3d":
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Manifest.dat", text)
        return buffer.getvalue()
    if fmt == "step":
        return f"ISO-10303-21;\nHEADER;\n/* {text} */\nENDSEC;\nEND-ISO-10303-21;\n".encode()
    if fmt == "stl":
        triangles = 2
        return text.encode()[:80].ljust(80, b" ") + struct.pack("<I", triangles) + b"\0" * (50 * triangles)
    if fmt == "iges":
        return (text[:72].ljust(72) + "S      1\n").encode()
    return f"700 0 1 0\n{text}\n".encode()


class ExportManager:
    def __init__(self, design):
        self._design = design
        self.fail_formats = set()
        self.failures = {}
        self.executed = []
        self.stl_unit_type_supported = True  # False: simulate an older Fusion

    def createFusionArchiveExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("f3d", path, geometry)

    def createSTEPExportOptions(self, path, geometry=None):  # noqa: N802
        return STEPExportOptions(path, geometry)

    def createIGESExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("iges", path, geometry)

    def createSATExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("sat", path, geometry)

    def createSTLExportOptions(self, geometry, path):  # noqa: N802
        cls = STLExportOptions if self.stl_unit_type_supported else LegacySTLExportOptions
        return cls(path, geometry)

    def execute(self, options):
        self.executed.append(options)
        mode = self.failures.get(options.format)
        if options.format in self.fail_formats or mode == "false":
            return False
        if mode == "raise":
            raise RuntimeError(f"simulated {options.format} export error")
        if mode == "missing":
            return True
        label = getattr(options.geometry, "name", None) or self._design.rootComponent.name
        data = b"" if mode == "empty" else _content(options.format, label)
        if mode == "corrupt":
            data = b"not a real file\n"
        with open(options.filename, "wb") as fh:
            fh.write(data)
        return True


class DataFile:
    def __init__(self, file_id, version_number=1):
        self.id = file_id
        self.versionNumber = version_number


class Document:
    def __init__(self, data_file=None, is_modified=False):
        self.dataFile = data_file
        self.isModified = is_modified


class Design:
    _CLASS_TYPE = "adsk::fusion::Design"

    def __init__(self, name="Bracket", file_id="urn:adsk.wipprod:dm.lineage:bracket", bodies=("Body1",)):
        self.objectType = self._CLASS_TYPE
        self.rootComponent = Component(name, list(bodies))
        self.parentDocument = Document(DataFile(file_id) if file_id else None)
        self.exportManager = ExportManager(self)

    @staticmethod
    def classType():  # noqa: N802
        return Design._CLASS_TYPE
