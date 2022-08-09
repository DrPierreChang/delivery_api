import logging
import pprint

pp = pprint.PrettyPrinter(indent=4)


class PageIterator(object):
    def __init__(self, make_call, host, url, auth, builder):
        self._url = url
        self._host = host
        self._auth = auth
        self._builder = builder
        self._current_page = 0
        self._page = None
        self._meta = None

        self._make_call = make_call

    def __iter__(self):
        return self

    def next(self):
        if not self._url:
            raise StopIteration

        logging.info('Getting a new page by url: %s' % self._url)

        data = self._make_call(self._url, self._auth).json()

        self._meta = data['meta']
        if self._meta['total_count'] > 0:
            stay_to_get = max(self._meta['total_count'] - (self._meta['offset'] + self._meta['limit']), 0)
            ready_percent = 100.0 * stay_to_get / self._meta['total_count']
            logging.info('Stay to get %s (total ready %0.2f%%)' % (stay_to_get, 100.0 - ready_percent))
        else:
            logging.info('Objects array is empty. It is the last page.')

        if self._meta.get('next', None):
            self._url = self._host + self._meta.get('next')
        else:
            self._url = None

        objects = [self._builder(raw_data) for raw_data in data['objects']]
        self._current_page += 1

        return objects


class ItemIterator(object):
    def __init__(self, make_call, host, url, auth, builder, pack=False):
        self._host = host
        self._page_iterator = PageIterator(make_call, host, url, auth, builder)
        self._items = None
        self._item_index = 0
        self._pack = pack

    def _get_by_pack(self):
        self._items = self._page_iterator.next()

        if not self._items:
            raise StopIteration

        return self._items

    def _get_by_items(self):
        if not self._items or self._item_index == len(self._items) - 1:
            del self._items
            self._items = self._page_iterator.next()
            self._item_index = -1

        if not self._items:
            raise StopIteration

        self._item_index += 1
        return self._items[self._item_index]

    def next(self):
        if not self._pack:
            result = self._get_by_items()
        else:
            result = self._get_by_pack()
        return result


class ObjectFromDict(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    @classmethod
    def build_from_dict(cls, d):
        if isinstance(d, dict):
            return cls(**d)
        raise AttributeError('You must provide the dict object as argument')

    def __str__(self):
        return str(self.__dict__)


class CustomerInterface(object):
    def get_name(self):
        raise NotImplementedError

    def get_phone(self):
        raise NotImplementedError

    def get_email(self):
        raise NotImplementedError


class OrderInterface(object):
    def get_title(self):
        raise NotImplementedError

    def get_comment(self):
        raise NotImplementedError

    def get_deliver_before(self):
        raise NotImplementedError
