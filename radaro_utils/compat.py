import sys

if sys.version_info > (3, 0):
    _range = range
else:
    _range = xrange

range = _range
