class CurrentAPIVersionDefault:
    api_version = None

    def set_context(self, serializer_field):
        self.api_version = serializer_field.context['request'].version

    def __call__(self):
        return self.api_version

    def __repr__(self):
        return self.__class__.__name__
