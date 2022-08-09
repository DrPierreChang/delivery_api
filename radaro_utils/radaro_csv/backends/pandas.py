from __future__ import absolute_import, unicode_literals

import copy
from datetime import datetime

import pandas as pd

from radaro_utils.radaro_csv.module_settings import settings

from .base import BaseReadBackend, BaseWriteBackend, PagingBackend


class BasePandasCSVBackend(object):
    # Columns array
    columns = None
    # Name of columns with dates
    parse_dates = []
    # Dict of types
    types = {}

    chunksize = None

    def __init__(self):
        self.pandas_chunksize = settings.PANDAS_CHUNKSIZE

    # Meta should contain columns which can be either list or dict, dict can have type mapping
    # If you want to have type mapping, check your order of keys.
    def init_meta(self, meta):
        self.parse_dates = []
        self.types = {}
        if meta.columns:
            if isinstance(meta.columns, list):
                self.columns = copy.deepcopy(meta.columns)
            elif isinstance(meta.columns, dict):
                for k, v in meta.columns.items():
                    if isinstance(v, datetime):
                        self.parse_dates.append(k)
                    else:
                        self.types[k] = v
                self.columns = list(meta.columns.keys())
        self.encoding = meta.encoding
        self.chunksize = meta.chunksize or self.pandas_chunksize


class PandasCSVBackend(BasePandasCSVBackend, PagingBackend, BaseReadBackend):
    csv = None

    def open(self, file_obj, meta):
        super(PandasCSVBackend, self).open(file_obj, meta)
        kwargs = {}
        kwargs['usecols'] = self.columns
        if self.pandas_chunksize:
            # assert not self.pandas_chunksize % self.chunksize, 'Pandas chunksize should be multiple of chunksize.'
            kwargs['chunksize'] = self.chunksize
        kwargs['dtype'] = self.types
        kwargs['parse_dates'] = self.parse_dates
        self.csv = pd.read_csv(file_obj, encoding=self.encoding, **kwargs)
        return self

    def __iter__(self):
        if self.pandas_chunksize:
            for df in self.csv:
                yield df
        else:
            yield self.csv


class PandasWritingCSVBackend(BasePandasCSVBackend, BaseWriteBackend):
    write_kwargs = None
    blocks = None

    def open(self, file_obj, meta):
        super(PandasWritingCSVBackend, self).open(file_obj, meta)
        self.file_obj = file_obj
        self.write_kwargs = {
            'columns': self.columns,
            'header': True,
            'mode': 'a',
            'index': False,
            'encoding': self.encoding
        }

    def write_data(self, data_to_write, **kwargs):
        """
        :param data_to_write: Iterable
        :param kwargs: dict
        :return:
        """
        for ind, block in enumerate(data_to_write):
            yield ind, self.write_block(block, header=ind < 1, **kwargs)

    def write_block(self, block, **kwargs):
        """
        :param block: pandas.DataFrame
        :param kwargs: dict
        :return:
        """

        # Sometimes columns required in csv are not present in DataFrame.
        # Such columns are added here
        existing_columns = block.columns.tolist()
        expected_columns = self.write_kwargs['columns']
        missing_columns = list(set(expected_columns) - set(existing_columns))
        block = block.reindex(columns=existing_columns + missing_columns)

        block.to_csv(self.file_obj, **dict(self.write_kwargs, **kwargs))


__all__ = ['PandasCSVBackend', 'PandasWritingCSVBackend']
