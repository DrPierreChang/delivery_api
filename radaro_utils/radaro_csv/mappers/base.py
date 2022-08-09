from __future__ import absolute_import, unicode_literals

from six.moves import reduce


class BaseMapper(object):
    def __call__(self, value):
        return value

    def prepare_columns(self, model_obj):
        raise NotImplementedError()


class RenameMixin(object):
    def head_remapper(self, k):
        raise NotImplementedError()


class BaseFilter(object):
    def __init__(self, mapper):
        self._mapper = mapper

    def filter(self, value):
        raise NotImplementedError()


# Basic mapper which push iterable through specified filters
class FlowMapper(BaseMapper):
    filter_flow = ()

    def __init__(self):
        self.basic_flow = [f(self) for f in self.filter_flow]

    def __call__(self, value):
        return reduce(lambda val, f: f.filter(val), self.basic_flow, value)
