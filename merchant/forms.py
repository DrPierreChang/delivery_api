from django.core.exceptions import ValidationError
from django.forms.fields import MultipleChoiceField

from constance import config

from .models import Merchant


class AllowedCountriesMultipleChoiceField(MultipleChoiceField):
    def validate(self, value):
        removed_countries = list(set(config.ALLOWED_COUNTRIES) - set(value))
        merchants_with_removed_countries = Merchant.objects.filter(countries__overlap=removed_countries)

        if merchants_with_removed_countries.exists():
            message = 'Merchants %s have countries you want to disable. Change countries of these merchants first.' % (
                ', '.join(map(str, merchants_with_removed_countries)),
            )
            raise ValidationError(message)

        return super(AllowedCountriesMultipleChoiceField, self).validate(value)
