"""SIMULATED Autodesk Fusion API for tests — not the real ``adsk`` package.

These test doubles model only the parts of the Fusion API that the add-in
uses, closely enough to drive the dialog and lifecycle code outside Fusion.
Passing tests here show the add-in's own logic is right; they do **not**
show that real Fusion behaves the way these fakes assume. Those assumptions
are listed in tests/fakes/README.md and checked by the manual Fusion
checklist.
"""

from . import cam, core, fusion  # noqa: F401

auto_terminate_calls = []
do_events_calls = 0


def autoTerminate(flag):  # noqa: N802 - Fusion's name
    auto_terminate_calls.append(bool(flag))


def doEvents():  # noqa: N802 - Fusion's name
    global do_events_calls
    do_events_calls += 1
