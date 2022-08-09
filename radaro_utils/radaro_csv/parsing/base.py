from radaro_utils import helpers

from ...utils import shortcut_link_safe
from .. import meta
from ..exceptions import MissingRequiredHeadersException


class BaseCSVModelMappingPipe(object):
    """
    This is the linking between data and backend. Here we collect meta data for backend and open the file.
    Mapper is responsible for collecting columns information (type and order) and CSV model object is
    responsible for encoding of the file.
    """
    backend = None
    mapper_class = None

    _file = None

    def __init__(self, model_obj, **kwargs):
        self.mapper = self._initialize_mapper()
        self.model_obj = model_obj
        self._file = self.model_obj.open_file()
        self._meta = self._initialize_meta(**kwargs)

    def _initialize_mapper(self):
        return self.mapper_class()

    def _initialize_meta(self, **kwargs):
        try:
            columns = self.mapper.prepare_columns(self.model_obj)
        except MissingRequiredHeadersException as ex:
            self.finish()
            raise MissingRequiredHeadersException(fields=ex.fields)
        _meta = meta.CSVMetaData()
        _meta.write_metadata(columns=columns, encoding=self.model_obj.encoding, **kwargs)
        return _meta

    def finish(self):
        self.model_obj.close_file(self._file)


class ChunkReaderMixin(BaseCSVModelMappingPipe):
    _chunk_iter = None
    _page = 0

    _assertion_page_consistence = 'You can only start from index: {}'
    _assertion_pagesize_consistence = 'Backend initialized with page size: {}'
    _assertion_paging_supported = 'Backend does not support chunks.'

    def __init__(self, *args, **kwargs):
        super(ChunkReaderMixin, self).__init__(*args, **kwargs)
        assert hasattr(self.backend, 'chunksize'), self._assertion_paging_supported

    def __getitem__(self, key):
        chunksize = key.stop - key.start
        if self._chunk_iter:
            assert self._meta.chunksize == chunksize, self._assertion_pagesize_consistence.format(self._meta.chunksize)
            assert self._page == float(key.start) / chunksize, self._assertion_page_consistence.format(int(self._page * chunksize))
        else:
            self._meta.chunksize = chunksize
            self.backend.open(self._file, self._meta)
            self._chunk_iter = iter(self.backend)
            self.next_block = self.next_page()
        mapped_block = self.mapper(self.next_block)
        try:
            self.next_block = self.next_page()
        except StopIteration:
            self.finish()
        finally:
            self._page += 1.
            return mapped_block

    def finish(self):
        super(ChunkReaderMixin, self).finish()
        self._chunk_iter = None

    def next_page(self):
        return next(self._chunk_iter)


class CSVModelMappingReader(ChunkReaderMixin, BaseCSVModelMappingPipe):
    def __iter__(self):
        self.backend.open(self._file, self._meta)
        for block in self.backend:
            for item in self.mapper(block):
                yield item
        self.finish()

    def __len__(self):
        return self.model_obj.lines - self.model_obj.blank_lines - 1


class QuerySetChunkMappingWriter(BaseCSVModelMappingPipe):
    queryset = None
    chunksize = None
    chunks = 0

    def get_queryset(self):
        return self.queryset

    @property
    def mapper_context(self):
        raise NotImplementedError()

    def using_context(self, context):
        raise NotImplementedError()

    def prepare(self, qs):
        qs_len = qs.count()
        self.chunks = int(qs_len / self.chunksize) + 1
        self.backend.open(self.model_obj.file, self._meta)
        return qs, qs_len

    def __iter__(self):
        qs, qs_len = self.prepare(self.get_queryset())
        with self.mapper.using_context(self.mapper_context) as mapper:
            data = (mapper(chunk) for chunk in helpers.chunks(qs, length=qs_len, n=self.chunksize))
            for res in self.backend.write_data(data):
                yield res
        self.finish()
