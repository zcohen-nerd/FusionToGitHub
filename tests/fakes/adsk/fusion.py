"""SIMULATED adsk.fusion: a design and its export manager.

``ExportManager.execute`` writes a small placeholder file at the requested
path; real Fusion writes the actual CAD file. Formats listed in
``ExportManager.fail_formats`` simulate an export that reports failure.
"""


class MeshRefinementSettings:
    MeshRefinementHigh = 0
    MeshRefinementMedium = 1
    MeshRefinementLow = 2


class ExportOptions:
    def __init__(self, fmt, path, geometry=None):
        self.format = fmt
        self.filename = path
        self.geometry = geometry
        self.meshRefinement = MeshRefinementSettings.MeshRefinementHigh


class ExportManager:
    def __init__(self, design):
        self._design = design
        self.fail_formats = set()
        self.executed = []

    def createFusionArchiveExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("f3d", path, geometry)

    def createSTEPExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("step", path, geometry)

    def createIGESExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("iges", path, geometry)

    def createSATExportOptions(self, path, geometry=None):  # noqa: N802
        return ExportOptions("sat", path, geometry)

    def createSTLExportOptions(self, geometry, path):  # noqa: N802
        return ExportOptions("stl", path, geometry)

    def execute(self, options):
        self.executed.append(options)
        if options.format in self.fail_formats:
            return False
        with open(options.filename, "w", encoding="utf-8") as fh:
            fh.write(f"simulated {options.format} export of {self._design.rootComponent.name}\n")
        return True


class Component:
    def __init__(self, name):
        self.name = name


class DataFile:
    def __init__(self, file_id):
        self.id = file_id


class Document:
    def __init__(self, data_file=None):
        self.dataFile = data_file


class Design:
    _CLASS_TYPE = "adsk::fusion::Design"

    def __init__(self, name="Bracket", file_id="urn:adsk.wipprod:dm.lineage:bracket"):
        self.objectType = self._CLASS_TYPE
        self.rootComponent = Component(name)
        self.parentDocument = Document(DataFile(file_id) if file_id else None)
        self.exportManager = ExportManager(self)

    @staticmethod
    def classType():  # noqa: N802
        return Design._CLASS_TYPE
