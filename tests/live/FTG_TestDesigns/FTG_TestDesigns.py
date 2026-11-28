"""Fusion script: create the designs used by the live verification campaign.

Run it in Fusion (UTILITIES → ADD-INS → Scripts tab → + → this folder → Run).
It creates three new, unsaved designs:

1. FTG Inch Cube      — inch display units, one 10 mm cube (checks J3: STL units).
2. FTG Multi Body     — two bodies in the root (one hidden) and a component with
                        a body of the same name (checks J4, J5: per-body STL).
3. FTG Plain          — a simple block, used as the linked component for J1/J2:
                        save it, then insert it into another saved design with
                        Insert → Insert into Current Design.

Save each one into a **test project** (File → Save) before using it. For J7,
save a copy named `Arm: v2/final?`.

Written against Fusion's documented API but **not yet run in Fusion**: if a
step fails, the message says which, and the designs made so far are kept.
It never saves, deletes or changes existing documents.
"""

import traceback

import adsk.core
import adsk.fusion

CM_PER_MM = 0.1  # Fusion's API works in centimetres


def _new_design(app):
    app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    return design


def _box(component, x_mm, y_mm, size_mm, name):
    """A cube of *size_mm* at (x_mm, y_mm) in *component*, as a new body named *name*."""
    sketch = component.sketches.add(component.xYConstructionPlane)
    corner = adsk.core.Point3D.create(x_mm * CM_PER_MM, y_mm * CM_PER_MM, 0)
    opposite = adsk.core.Point3D.create((x_mm + size_mm) * CM_PER_MM, (y_mm + size_mm) * CM_PER_MM, 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner, opposite)
    profile = sketch.profiles.item(sketch.profiles.count - 1)
    extrude = component.features.extrudeFeatures.addSimple(
        profile,
        adsk.core.ValueInput.createByReal(size_mm * CM_PER_MM),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    body = extrude.bodies.item(0)
    body.name = name
    return body


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    made = []
    step = "starting"
    try:
        step = "FTG Inch Cube"
        design = _new_design(app)
        design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.InchDistanceUnits
        _box(design.rootComponent, 0, 0, 10, "Cube 10mm")
        made.append(step)

        step = "FTG Multi Body"
        design = _new_design(app)
        root = design.rootComponent
        _box(root, 0, 0, 20, "Plate")
        hidden = _box(root, 40, 0, 10, "Hidden block")
        hidden.isLightBulbOn = False
        occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occurrence.component.name = "Arm"
        _box(occurrence.component, 0, 40, 15, "Plate")  # same name as the root's body
        made.append(step)

        step = "FTG Plain"
        design = _new_design(app)
        _box(design.rootComponent, 0, 0, 25, "Block")
        made.append(step)

        ui.messageBox("Created: " + ", ".join(made) + ".\n\nSave each into a test project (File → Save) "
                      "with the name shown, before using it in the campaign.", "FTG test designs")
    except Exception:
        ui.messageBox(f"Stopped while creating {step}.\nCreated so far: {', '.join(made) or 'none'}.\n\n"
                      + traceback.format_exc(), "FTG test designs")
