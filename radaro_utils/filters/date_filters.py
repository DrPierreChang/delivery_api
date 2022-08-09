from datetime import datetime, time, timedelta

from django.contrib import admin
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from daterange_filter.filter import FILTER_PREFIX, DateRangeFilter, clean_input_prefix


class DateTimeDescFilter(admin.SimpleListFilter):
    filtering_lookup = None
    alias_for_lookup = 'Value'

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'today':
                est_tz = timezone.pytz.timezone('EST')
                filtering_date = timezone.now().astimezone(est_tz)
                filtering_date = filtering_date.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                filtering_date = timezone.now() - timedelta(days=int(self.value()))
            return queryset.filter(**{self.filtering_lookup: filtering_date})

    def lookups(self, request, model_admin):
        return (
            ('today', _('{alias} for today (US EST timezone)'.format(alias=self.alias_for_lookup))),
            ('1', _('{alias} for 24+ hours ago'.format(alias=self.alias_for_lookup))),
            ('3', _('{alias} for 72+ hours ago'.format(alias=self.alias_for_lookup))),
            ('7', _('7 days')),
            ('30', _('Month')),
            ('90', _('3 months')),
            ('365', _('Year')),
        )


def date_to_datetime(day):
    return timezone.get_current_timezone().localize(datetime.combine(day, time.min))


class RadaroDateTimeRangeFilter(DateRangeFilter):
    def queryset(self, request, queryset):
        if self.form.is_valid():
            # get no null params
            filter_params = clean_input_prefix(dict(filter(lambda x: bool(x[1]), self.form.cleaned_data.items())))

            # filter by upto included
            lookup_upto = self.lookup_kwarg_upto.lstrip(FILTER_PREFIX)
            if filter_params.get(lookup_upto) is not None:
                lookup_kwarg_upto_value = filter_params.pop(lookup_upto)
                filter_params['%s__lt' % self.field_path] = lookup_kwarg_upto_value + timedelta(days=1)

            # convert date params to datetime params
            filter_params = {key: date_to_datetime(day) for key, day in filter_params.items()}

            return queryset.filter(**filter_params)
        else:
            return queryset
