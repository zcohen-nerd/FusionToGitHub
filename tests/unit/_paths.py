"""Make src/ and tests/fakes importable for the unit tests."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (os.path.join(_HERE, "..", "..", "src"), os.path.join(_HERE, "..", "fakes")):
    _path = os.path.normpath(_path)
    if _path not in sys.path:
        sys.path.insert(0, _path)


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
