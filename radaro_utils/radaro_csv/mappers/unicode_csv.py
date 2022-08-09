from __future__ import absolute_import, unicode_literals

from .base import BaseFilter, FlowMapper, RenameMixin


class OmitEmptyAndUnknownFilter(BaseFilter):
    def filter(self, value):
        return ({c: row[c] for c in self._mapper.found_columns if row[c] != ''} for row in value)


class BaseUnicodeCSVMapper(RenameMixin, FlowMapper):
    filter_flow = (OmitEmptyAndUnknownFilter,)
