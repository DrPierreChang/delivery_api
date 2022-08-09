class MapsAPIClientFactory:
    @staticmethod
    def create(google_api_key, timeout, channel, proxies=None, *args, **kwargs):
        raise NotImplementedError()


class empty(object):
    pass
