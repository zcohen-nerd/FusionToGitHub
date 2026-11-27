"""Make src/ and tests/fakes importable for the unit tests."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (os.path.join(_HERE, "..", "..", "src"), os.path.join(_HERE, "..", "fakes")):
    _path = os.path.normpath(_path)
    if _path not in sys.path:
        sys.path.insert(0, _path)
