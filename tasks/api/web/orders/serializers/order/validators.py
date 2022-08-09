from django.utils.translation import gettext_lazy as _

from rest_framework import serializers


class JobIntervalsValidator:
    instance = None

    def set_context(self, serializer):
        self.instance = getattr(serializer, 'instance', None)

    def __call__(self, attrs):
        merchant = attrs.get('merchant', None) or self.instance.merchant
        tz = merchant.timezone
        self._validate_times(
            attrs, tz, ('pickup_after', _('Pick up after')), ('pickup_before', _('Pick up deadline'))
        )
        self._validate_times(
            attrs, tz, ('deliver_after', _('Deliver after')), ('deliver_before', _('Deliver deadline'))
        )
        self._validate_times(
            attrs, tz, ('pickup_before', _('Pick up deadline')), ('deliver_before', _('Deliver deadline'))
        )

    def _validate_times(self, attrs, tz, lower_detail, upper_detail):
        lower_field, lower_label = lower_detail
        upper_field, upper_label = upper_detail

        if lower_field not in attrs and upper_field not in attrs:
            return

        lower = attrs.get(lower_field, None)
        upper = attrs.get(upper_field, None)

        if self.instance is not None:
            lower = lower or getattr(self.instance, lower_field, None)
            upper = upper or getattr(self.instance, upper_field, None)

        if lower and upper:
            if lower >= upper:
                raise serializers.ValidationError(_('{lower_label} cannot be later than {upper_label}')
                                                  .format(lower_label=lower_label, upper_label=upper_label))
            if lower.astimezone(tz).date() != upper.astimezone(tz).date():
                raise serializers.ValidationError(_('{lower_label} and {upper_label} must be within one day')
                                                  .format(lower_label=lower_label, upper_label=upper_label))
