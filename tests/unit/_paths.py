"""Load the add-in (src/) as a package, with the simulated Fusion API, for the unit tests.

See tests/addin_package.py: src/ itself is never put on sys.path.
"""

import os
import sys

_TESTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import addin_package  # noqa: E402

addin_package.install()


def force_rmtree(path):
    """Delete a test folder completely, including Git's read-only object files.

    On Windows, Git marks object files read-only and shutil.rmtree can't delete
    them, so test folders were silently left behind. Clear the flag and retry.
    """
    import shutil
    import stat
    import time

    def _clear_readonly(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            func(target)
        except OSError:
            pass

    for attempt in range(5):
        if not os.path.exists(path):
            return
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_clear_readonly)
        else:
            shutil.rmtree(path, onerror=_clear_readonly)
        if not os.path.exists(path):
            return
        time.sleep(0.2 * (attempt + 1))
