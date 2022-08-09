import sys

if sys.version_info > (3, 0):
    import functools as fn_
    _range = range
    _reduce = fn_.reduce
else:
    _range = xrange
    _reduce = reduce


class CompatModule(object):
    range = _range
    reduce = _reduce
