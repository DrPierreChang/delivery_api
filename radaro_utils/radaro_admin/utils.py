def build_field_attrgetter(field, **kwargs):
    def func(self, obj):
        for attr_name in field.split('.'):
            obj = getattr(obj, attr_name)
            if obj is None:
                return
        return obj
    for key, value in kwargs.items():
        setattr(func, key, value)
    return func
