# Simulated Fusion API (`tests/fakes/adsk`)

These are **test doubles, not Fusion**. They let `tests/unit/test_dialog.py`
and `tests/unit/test_addin_lifecycle.py` drive the add-in's real dialog and
lifecycle code outside Fusion. A passing test shows that the add-in's own
logic is right, *if* Fusion behaves the way these fakes assume. Each
assumption below must be confirmed in Fusion itself (see the manual
checklist in `tests/MANUAL_TESTS.md`).

## Assumptions about Fusion

1. Input ids are unique per command. Adding a second input with an existing id
   fails (the fake raises), and `deleteMe()` frees the id.
2. `TableCommandInput.clear()` detaches rows but doesn't delete their inputs.
   The 4-argument form `addTableCommandInput(id, name, columns, ratio)` exists.
3. A `TextListDropDownStyle` dropdown is single-select: selecting an item
   deselects the others. `CheckBoxDropDownStyle` is multi-select.
   `listItems.clear()` empties the list.
4. Changing an input's value from code does **not** fire `inputChanged`; only
   user actions do. The dialog refreshes itself after programmatic changes.
5. `StringValueCommandInput.isPassword = True` masks the field (dots).
6. Setting `executeFailed = True` in the execute handler keeps the dialog open.
7. `messageBox(text, title, YesNoButtonType)` returns `DialogResults.DialogYes`
   or `DialogNo`; `YesNoCancelButtonType` can also return `DialogCancel`.
8. `inputBox(prompt, title, default)` returns `(value, cancelled)`.
9. `createProgressDialog()` can be shown, hidden and shown again, and a
   `messageBox` opened while it's hidden is visible to the user.
10. `addCommand(definition, id)` fails if a control with that id already
    exists in the panel, so the add-in deletes stale controls first.
11. `design.parentDocument.dataFile.id` is stable across renames of a saved
    design, and `dataFile` is `None` for a design that was never saved.
12. `exportManager.execute(options)` returns `True` and writes the file at
    `options.filename` when it succeeds.
13. `adsk.doEvents()` can be called between git steps without side effects.

## Exports and design structure (S4)

`adsk.fusion` in these fakes is a simulation of the design structure and the
export manager. It writes small files that only *look like* each format, so
the add-in's basic file checks (`src/export_checks.py`) can run:

| Format | What the fake writes |
|--------|----------------------|
| f3d    | a ZIP with one `Manifest.dat` entry |
| step   | an `ISO-10303-21;` header and footer |
| stl    | a complete binary STL (80-byte header, count, 2 triangles) |
| iges   | one 80-column start (`S`) record |
| sat    | a line of text |

None of these files can be opened in a CAD program. Failure injection:
`design.exportManager.failures[fmt]` is `"raise"`, `"false"`, `"empty"`,
`"missing"` or `"corrupt"`; `fail_formats` is the older spelling of
`"false"`. `exportManager.stl_unit_type_supported = False` simulates a Fusion
version whose `STLExportOptions` has no `unitType`.

`Component.add_occurrence(component, linked=..., broken=...)` and
`Occurrence.add_occurrence(...)` build assemblies; they are test helpers, not
Fusion API (Fusion uses `occurrences.addNewComponent` and friends).

Assumptions about Fusion, to confirm in Fusion itself:

14. `rootComponent.allOccurrences` lists every occurrence at every depth,
    and `Occurrence.isReferencedComponent` is `True` for a component inserted
    from another document. Reading it can raise for a reference Fusion can't
    resolve (the fake's `broken=True`). The fake also marks the children of a
    linked occurrence as linked.
15. `Occurrence.fullPathName` is the `+`-separated path of occurrence names
    (`Arm:1+Bolt:2`), and `Occurrence.bRepBodies` returns proxies of the
    component's bodies whose `isVisible` reflects the occurrence's visibility.
16. `createSTLExportOptions(body, path)` exports one body, and a body proxy
    exports at its position in the assembly (a community report says bodies
    in components may export at the component's own origin instead).
17. `STLExportOptions.unitType` exists in recent Fusion builds and accepts
    `adsk.fusion.DistanceUnits.MillimeterDistanceUnits`; older builds have no
    such attribute.
18. `exportManager.execute` returns `False`, or raises, when an export fails,
    and Fusion's `.f3d` export does not bundle linked components (there is
    no documented API for a self-contained `.f3z`).
