class BackendRegistry:
    _map = {}

    def register(self, name):
        def wrapper(backend_class):
            self._map[name] = backend_class
            return backend_class
        return wrapper

    def get(self, name):
        backend_class = self._map.get(name, False)
        if not backend_class:
            raise Exception('Backend class is not registered under this name: {}'.format(name))
        return backend_class


backend_registry = BackendRegistry()
