class SerializerMapper(object):
    EXTERNAL = 'external'
    CSV = 'csv'

    _map = {}

    allowed_names = (EXTERNAL, CSV)

    def register(self, name):
        def registrator(Serializer):
            if name not in self.allowed_names:
                raise Exception('Please specify serializer name in allowed names')
            self._map[name] = Serializer
            return Serializer
        return registrator

    def get(self, name):
        serializer_class = self._map.get(name, False)
        if not serializer_class:
            raise Exception('Serializer is not registered under this name: {}'.format(name))
        return serializer_class


prototype_serializers = SerializerMapper()
