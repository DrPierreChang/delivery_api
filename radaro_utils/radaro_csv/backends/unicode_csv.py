from __future__ import absolute_import, unicode_literals

import csv
import itertools as it_

from .base import BaseReadBackend, BaseWriteBackend, PagingBackend


# TODO: doesn't work after porting to python3: problem in fields mapping
class UnicodeCSVReadBackend(PagingBackend, BaseReadBackend):
    columns = None
    types = None
    reader = None

    def init_meta(self, meta):
        self.encoding = meta.encoding
        self.chunksize = meta.chunksize
        if isinstance(meta.columns, list):
            self.columns = meta.columns
        elif isinstance(meta.columns, dict):
            self.types = meta.columns
            self.columns = meta.columns.keys()

    def open(self, file_obj, meta):
        super(UnicodeCSVReadBackend, self).open(file_obj, meta)
        self.reader = csv.DictReader(file_obj)
        self.reader.fieldnames = self.columns

    def __iter__(self):
        if self.chunksize:
            for _ in it_.repeat(None):
                yield (next(self.reader) for _ in range(self.chunksize))
        else:
            yield self.reader


class UnicodeCSVWriteBackend(BaseWriteBackend):
    writer = None
    columns = None

    def init_meta(self, meta):
        assert isinstance(meta.columns, list)
        self.columns = meta.columns
        self.encoding = meta.encoding

    def open(self, file_obj, meta):
        super(UnicodeCSVWriteBackend, self).open(file_obj, meta)
        self.writer = csv.DictWriter(file_obj, fieldnames=self.columns)

    def write_block(self, block, **kwargs):
        """
        :param block: dict
        :param kwargs: dict
        :return:
        """
        self.writer.writerow(block)

    def write_data(self, data_to_write, **kwargs):
        """
        :param data_to_write: Iterable[dict]
        :param kwargs:
        :return:
        """
        self.writer.writeheader()
        return super(UnicodeCSVWriteBackend, self).write_data(data_to_write, **kwargs)


__all__ = ['UnicodeCSVReadBackend', 'UnicodeCSVWriteBackend']
