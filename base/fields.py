import json
from datetime import date, datetime

from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.forms import JSONField as JSONFormField
from django.core import exceptions
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class OneTimeValuesFormField(JSONFormField):
    default_error_messages = {
        'invalid': _("'%(value)s' value must be valid JSON."),
        'invalid_key_admin_page': _('All keys must be in YYYY-MM-DD format.'),
        'invalid_key': _('All keys must be days.'),
        'not_dict': _('Data must be in key-value format.'),
    }

    def prepare_value(self, value):
        try:
            value = {day.isoformat(): one_time_value for day, one_time_value in value.items()}
        except AttributeError:
            pass
        return json.dumps(value)

    def to_python(self, value):
        value = super().to_python(value)

        if not isinstance(value, dict):
            raise exceptions.ValidationError(
                self.error_messages['not_dict'],
                code='not_dict',
            )

        try:
            result = {
                datetime.strptime(day, '%Y-%m-%d').date(): one_time_value
                for day, one_time_value in value.items()
            }
        except ValueError as exc:
            raise exceptions.ValidationError(
                self.error_messages['invalid_key_admin_page'],
                code='invalid_key_admin_page',
            )

        return result

    def has_changed(self, initial, data):
        if super(JSONFormField, self).has_changed(initial, data):
            return True

        data = self.to_python(data)
        return initial != data


class OneTimeValuesField(JSONField):
    def __init__(self, *args, **kwargs):
        kwargs['default'] = dict
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs['default']
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if not value:
            return {}
        result = {date.fromordinal(int(day)): one_time_value for day, one_time_value in value.items()}
        return result

    def _prepare_for_saving(self, value):
        if value.get('prepared_for_saving', False):
            return value

        if not isinstance(value, dict):
            raise exceptions.ValidationError(
                self.error_messages['not_dict'],
                code='not_dict',
            )
        if not all(map(lambda key: isinstance(key, date), value.keys())):
            raise exceptions.ValidationError(
                self.error_messages['invalid_key'],
                code='invalid_key',
            )

        result = {
            str(day.toordinal()): one_time_value
            for day, one_time_value in value.items()
            if day >= timezone.now().date() - timezone.timedelta(days=1)
        }

        result['prepared_for_saving'] = True
        return result

    def to_python(self, value):
        return self._prepare_for_saving(value)

    def get_prep_value(self, value):
        value = self._prepare_for_saving(value)
        del value['prepared_for_saving']
        return super().get_prep_value(value)

    def formfield(self, **kwargs):
        return super().formfield(**{
            'form_class': OneTimeValuesFormField,
            **kwargs,
        })
