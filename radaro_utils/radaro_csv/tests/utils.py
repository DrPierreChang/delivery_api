import os
from collections import namedtuple

from radaro_utils.radaro_csv import meta

# from radaro_utils.radaro_csv.mappers import DictToPandasMapper

base_path = os.path.dirname(__file__)
file_path = os.path.join(base_path, 'RADARO_CSV_REPORT.csv')


Customer = namedtuple('Customer', 'name phone email')
Order = namedtuple('Order', 'deliver_before driver_id title deliver_address customer comment')


class FakeCSVModel(meta.CSVMetadataMixin):
    _f = None

    def open_file(self, mode='rt'):
        if not self._f:
            self._f = open(file_path, mode)
        else:
            self._f.seek(0)
        return self._f

    def close_file(self, _file):
        _file.seek(0)


class FakeWriteCSVModel(FakeCSVModel):
    @property
    def encoding(self):
        return 'utf-8'

    @encoding.setter
    def encoding(self, val):
        pass

    def open_file(self, mode='wt'):
        return super(FakeWriteCSVModel, self).open_file(mode)

    def close_file(self, _file):
        _file.close()
        self._f = None


test_array = ['One', 'Two', 'Three', 'Four']


# class SimpleDictToPandasMapper(DictToPandasMapper):
#     def columns(self):
#         return test_array
