from django.conf import settings


class ModelMapper(object):
    _mapping = {}
    _detailed_mapping = {ver: {} for ver in (1, 2, 'web')}
    _converter_mapping = {ver: {} for ver in (1, 2, 'web')}

    def register_serializer(self, serializer_class):
        model_class = serializer_class.Meta.model
        self._mapping[model_class] = serializer_class
        return serializer_class

    def register_serializer_for_detailed_dump(self, version=1):
        def registrator(serializer_class):
            model_class = serializer_class.Meta.model
            self._detailed_mapping[version][model_class] = serializer_class
            return serializer_class
        return registrator

    def get_for_detailed_dump(self, model_class, version=1):
        return self._detailed_mapping[version].get(model_class, self._mapping[model_class])

    def serialize_detailed_for_all_versions(self, instance, context):
        Model = type(instance)
        data = {ver: self.get_for_detailed_dump(Model, version=ver)(instance, context=context).data
                for ver, serializers in self._detailed_mapping.items()}
        return data

    def get_for(self, model_class):
        return self._mapping[model_class]

    def register_converter_for_obj_dump(self, model_class, version):
        def registrator(serializer_class):
            self._converter_mapping[version][model_class] = serializer_class
            return serializer_class

        return registrator

    def get_converter_for_obj_dump(self, model_class, version=1):
        return self._converter_mapping[version].get(model_class, None)


serializer_map = ModelMapper()
