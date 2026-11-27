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
