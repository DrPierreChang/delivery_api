from __future__ import absolute_import, unicode_literals

from functools import partial

from django.db import connection

import pandas as pd

from .base import BaseFilter, FlowMapper, RenameMixin


# Read filters
class RenameDataFrameFilter(BaseFilter):
    def filter(self, value):
        return value.rename(self._mapper.head_remapper, axis='columns')


class FilterNAFilter(BaseFilter):
    def filter(self, value):
        return ({k: v for k, v in item.items() if pd.notna(v)} for item in value)


class DataFrameToDictFilter(BaseFilter):
    def filter(self, value):
        return value.to_dict(orient='rows')


# Write filters
class QuerySetToDataFrameFilter(BaseFilter):
    def filter(self, state):
        sql, sql_params = state.values_list(self._mapper.index_col, *self._mapper.columns) \
            .query.get_compiler(using=state.db).as_sql()
        df = pd.read_sql(sql, connection, params=sql_params, index_col=self._mapper.index_col)
        return df


class FormatDateDataFrameFilter(BaseFilter):
    def filter(self, value):
        date_fields = self._mapper.date_fields
        df = value
        for date_field in date_fields['columns']:
            try:
                dt = df[date_field].dt
                df[date_field] = dt.tz_convert(self._mapper.timezone).dt.strftime(
                    date_fields['formats'][date_field])
                df[date_field] = df[date_field].replace({'NaT': ''})
            except AttributeError:
                continue
        return df


class PandasToDictMapper(RenameMixin, FlowMapper):
    """
    DataFrame ==> ({head_remapper(k):v<NON_NAN>})
    """
    filter_flow = (RenameDataFrameFilter, DataFrameToDictFilter, FilterNAFilter)


class QuerySetToDataFrameChunksMapper(RenameMixin, FlowMapper):
    index_col = 'id'

    filter_flow = (
        QuerySetToDataFrameFilter,
        RenameDataFrameFilter
    )
