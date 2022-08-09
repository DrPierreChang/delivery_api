from django.contrib.contenttypes.models import ContentType


class ContextMerchantDefault:
    merchant = None

    def set_context(self, serializer_field):
        self.merchant = serializer_field.parent.context['merchant']

    def __call__(self):
        return self.merchant

    def __repr__(self):
        return self.__class__.__name__


class ExternalSourceIDDefault:
    auth = None

    def set_context(self, serializer_field):
        self.auth = serializer_field.context['request'].auth

    def __call__(self):
        return self.auth.id

    def __repr__(self):
        return self.__class__.__name__


class ExternalSourceTypeDefault:
    auth = None

    def set_context(self, serializer_field):
        self.auth = serializer_field.context['request'].auth

    def __call__(self):
        source_type = ContentType.objects.get_for_model(type(self.auth))
        return source_type.id

    def __repr__(self):
        return self.__class__.__name__
