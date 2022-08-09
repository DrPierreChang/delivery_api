from django.core.exceptions import ValidationError

import django_filters
from django_filters import fields

return_empty_result = object()


class ModelMultipleChoiceField(fields.ModelMultipleChoiceField):
    def _check_values(self, value):
        try:
            qs = super(ModelMultipleChoiceField, self)._check_values(value)
        except ValidationError as exc:
            if exc.code == 'invalid_choice':  # should pass invalid_choice check
                key = self.to_field_name or 'pk'
                qs = self.queryset.filter(**{'%s__in' % key: value})
            else:
                raise

        result = set(qs)
        return result if len(result) > 0 else return_empty_result


class RadaroModelMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = ModelMultipleChoiceField

    def filter(self, qs, value):
        if value == return_empty_result:
            return qs.none()
        return super().filter(qs, value)
