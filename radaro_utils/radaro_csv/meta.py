from __future__ import absolute_import, unicode_literals

import codecs
import csv

import cchardet

from radaro_utils.radaro_csv.exceptions import CSVEncodingError


class CSVMetaData(object):
    def write_metadata(self, columns=None, encoding=None, lines=None, blank_lines=None, chunksize=None):
        self.columns = columns
        self.encoding = encoding
        self.lines = lines
        self.blank_lines = blank_lines
        self.chunksize = chunksize
        return self


class CSVMetadataMixin(CSVMetaData):
    _opened_file = None

    def detect_columns(self, _file, encoding):
        columns = csv.DictReader(codecs.iterdecode(_file, encoding)).fieldnames
        return columns

    def open(self, mode='rt'):
        self._opened_file = self.open_file(mode)
        return self

    def __enter__(self):
        return self._opened_file

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_file(self._opened_file)
        self._opened_file = None

    def open_file(self, mode='rt'):
        raise NotImplementedError()

    def close_file(self, _file):
        _file.close()

    def detect_metadata(self):
        _file = self.open_file()
        encoding = self.detect_encoding(_file)
        _file.seek(0)
        lines = self.detect_lines(_file, encoding)
        _file.seek(0)
        columns = self.detect_columns(_file, encoding)
        _file.seek(0)
        return self.write_metadata(columns,
                                   encoding,
                                   sum(lines.values()),
                                   lines['blank_before'] + lines['blank_after'])

    def detect_encoding(self, _file):
        detector = cchardet.UniversalDetector()
        detector.reset()
        for line in _file.readlines():
            if line:
                detector.feed(line)
        detector.close()
        try:
            encoding = detector.result['encoding'].lower()
        except AttributeError:
            raise CSVEncodingError()

        # Sometimes the detector defines the text encoding as "viscii", which is not supported by python
        # The encodings "viscii" and "cp1258" are Vietnamese
        if encoding == 'viscii':
            return 'cp1258'
        return encoding

    def detect_lines(self, _file, encoding):
        lines = {'num': 0, 'blank_before': 0, 'blank_after': 0}
        _reader = csv.reader(codecs.iterdecode(_file, encoding))
        for ind, line_array in enumerate(_reader):
            line = _reader.dialect.delimiter.join(line_array).strip()
            if line:
                lines['num'] += 1
            else:
                blank_update = 'blank_before' if not lines['num'] else 'blank_after'
                lines[blank_update] += 1
        return lines

    def get_metadata(self):
        return self
