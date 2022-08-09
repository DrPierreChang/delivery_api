# Basic backend should have encoding of file and ability of preparation for operations
class BaseBackend(object):
    encoding = None

    def init_meta(self, meta):
        raise NotImplementedError()

    def open(self, file_obj, meta):
        self.init_meta(meta)


# Basic read backend is iterable
class BaseReadBackend(BaseBackend):
    def __iter__(self):
        raise NotImplementedError()


class BaseWriteBackend(BaseBackend):
    blocks = None

    def write_block(self, block, **kwargs):
        raise NotImplementedError()

    def write_data(self, data_to_write, **kwargs):
        for ind, block in enumerate(data_to_write):
            yield ind, self.write_block(block, **kwargs)


class PagingBackend(object):
    chunksize = None
