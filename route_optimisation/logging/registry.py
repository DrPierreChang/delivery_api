class LogItemRegistry:
    _map = {}

    def register(self):
        def wrapper(log_class):
            name = log_class.event
            self._map[name] = log_class
            return log_class
        return wrapper

    def get(self, name):
        return self._map.get(name, None)


log_item_registry = LogItemRegistry()
