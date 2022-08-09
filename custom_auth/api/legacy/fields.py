from rest_framework.fields import CharField


class CaseInsensitiveCharField(CharField):
    def to_internal_value(self, data):
        value = super(CaseInsensitiveCharField, self).to_internal_value(data)
        return value.lower()
