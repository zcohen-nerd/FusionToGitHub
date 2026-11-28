# Live campaign fixtures

Helpers that reduce manual work in the live verification campaign
([`../MANUAL_CHECKLIST.md`](../MANUAL_CHECKLIST.md)). Neither has been run in
Fusion or against GitHub yet; check what they did the first time.

| Helper | What it does |
|---|---|
| [`FTG_TestDesigns/`](FTG_TestDesigns/FTG_TestDesigns.py) | A Fusion script (UTILITIES → ADD-INS → Scripts → + → this folder → Run) that creates the test designs: an inch-unit design with a 10 mm cube (J3), a multi-body design with a hidden body and a component whose body has the same name as a root body (J4, J5), and a plain block to insert as a linked component (J1, J2). It never saves or changes existing documents; save the new ones into a test project yourself. |
| [`../../scripts/live/make_test_repos.py`](../../scripts/live/make_test_repos.py) | Creates disposable **private** repositories `ftg-live-<date>-a`, `-b`, and `-protected` (main protected, for U16) with the GitHub CLI, lists them, and deletes them after a typed confirmation. It never touches any other repository. |

Use a test GitHub account if you can, and a fine-grained token limited to the
`ftg-live-…` repositories for step 10.
