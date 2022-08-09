class ModelFieldDescriptor(object):
    cache_name = None
    single = False
    is_descriptor = True

    def __init__(self):
        if self.cache_name is None:
            raise NotImplementedError(u'`cache_name` must be defined.')

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self
        if not self.is_cached(instance):
            value = self.get_value_by_python(instance)
            setattr(instance, self.cache_name, value)
        return getattr(instance, self.cache_name)

    def is_cached(self, instance):
        return hasattr(instance, self.cache_name)

    def get_foreign_related_value(self, instance):
        raise NotImplementedError()

    def get_local_related_value(self, instance):
        raise NotImplementedError()

    def get_default_queryset(self):
        raise NotImplementedError()

    def filter_queryset(self, instances, queryset):
        raise NotImplementedError()

    def get_prefetch_queryset(self, instances, queryset=None):
        if queryset is None:
            queryset = self.get_default_queryset()

        rel_obj_attr = self.get_foreign_related_value
        instance_attr = self.get_local_related_value

        queryset = self.filter_queryset(instances, queryset)

        return queryset, rel_obj_attr, instance_attr, self.single, self.cache_name, self.is_descriptor

    def get_value_by_python(self, instance):
        raise NotImplementedError()
