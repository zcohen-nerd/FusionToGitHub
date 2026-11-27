# Simulated Fusion API (`tests/fakes/adsk`)

These are **test doubles, not Fusion**. They let `tests/unit/test_dialog.py`
and `tests/unit/test_addin_lifecycle.py` drive the add-in's real dialog and
lifecycle code outside Fusion. A passing test shows that the add-in's own
logic is right, *if* Fusion behaves the way these fakes assume. Each
assumption below must be confirmed in Fusion itself (see the manual
checklist in `tests/MANUAL_CHECKLIST.md`).

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
    (Since S4 the add-in no longer calls it during a push.)

### Events and threads (S4 background push)

14. Events keep only weak references to their handlers: a handler the add-in
    doesn't hold itself is collected and never called. The fake's `Event`
    holds weak references, so a missing reference fails the tests.
15. Fusion's API may only be used on its main thread (Autodesk's "Working in
    a Separate Thread" guide: don't call any Fusion API from a worker thread;
    even `messageBox` can crash). The fake refuses `messageBox`, `inputBox`,
    `createProgressDialog`, progress dialog use, `app.log` and custom event
    registration from any other thread, and the test harness fails a test
    that tried.
16. `app.registerCustomEvent(id)` returns an event you add a handler to;
    registering an id twice fails (the fake raises); `unregisterCustomEvent(id)`
    removes it. `app.fireCustomEvent(id, text)` may be called from any thread,
    returns False for an id that isn't registered, and **queues** the event:
    the handler runs later on the main thread, with `args.additionalInfo`
    being *text*. Events still queued when the id is unregistered are dropped.
    In tests, `app.process_events(timeout, until=...)` plays Fusion's message
    loop; nothing is delivered inside `fireCustomEvent`.
17. `ProgressDialog.show(title, message, minimumValue, maximumValue, delay)`
    takes integers; the last is a delay in seconds before the dialog appears.
    `cancelButtonText` labels the Cancel button and `wasCancelled` becomes
    True once the user presses it (`press_cancel()` in tests). The dialog
    stays responsive while the add-in's code is idle (the push runs in the
    background).
18. A command ends when OK is pressed and `executeFailed` stays False, or
    when it is cancelled; `destroy` is then fired and the dialog is gone.
    `validateInputs` fires after each `inputChanged`.
19. `StringValueCommandInput.value` is a `str` and
    `BoolValueCommandInput.value` a `bool`; other types raise.
20. Command definitions and toolbar controls created by another add-in (for
    example a second installed copy using the same command id) are visible
    through `commandDefinitions.itemById`.

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

21. `rootComponent.allOccurrences` lists every occurrence at every depth,
    and `Occurrence.isReferencedComponent` is `True` for a component inserted
    from another document. Reading it can raise for a reference Fusion can't
    resolve (the fake's `broken=True`). The fake also marks the children of a
    linked occurrence as linked.
22. `Occurrence.fullPathName` is the `+`-separated path of occurrence names
    (`Arm:1+Bolt:2`), and `Occurrence.bRepBodies` returns proxies of the
    component's bodies whose `isVisible` reflects the occurrence's visibility.
23. `createSTLExportOptions(body, path)` exports one body, and a body proxy
    exports at its position in the assembly (a community report says bodies
    in components may export at the component's own origin instead).
24. `STLExportOptions.unitType` exists in recent Fusion builds and accepts
    `adsk.fusion.DistanceUnits.MillimeterDistanceUnits`; older builds have no
    such attribute.
25. `exportManager.execute` returns `False`, or raises, when an export fails,
    and Fusion's `.f3d` export does not bundle linked components (there is
    no documented API for a self-contained `.f3z`).

26. A modal `messageBox` may let Fusion deliver other events (custom events
    from the background push) while it is open. The fake does that only when a
    test sets `ui.while_message_box_open`; the bridge must cope either way.
