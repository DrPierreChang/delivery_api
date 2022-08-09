import operator
from functools import reduce

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from rest_framework import pagination
from rest_framework.response import Response

from radaro_utils.countries import countries
from radaro_utils.radaro_phone.utils import phone_is_valid


class CardPaginationClass(pagination.PageNumberPagination):
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'balance': self.request.user.current_merchant.balance,
            'previous': self.get_previous_link(),
            'next': self.get_next_link(),
            'results': data
        })


class ReportsFrequencySettingsMixin(models.Model):
    DAILY = 'daily'
    WEEKLY = 'weekly'
    EVERY_TWO_WEEKS = 'two_weeks'
    MONTHLY = 'monthly'

    REPORT_FREQUENCY_RANGES = {
        DAILY: {'days': 1},
        WEEKLY: {'weeks': 1},
        EVERY_TWO_WEEKS: {'weeks': 2},
        MONTHLY: {'months': 1}
    }

    REPORT_FREQUENCY = (
        (DAILY, 'Daily'),
        (WEEKLY, 'Weekly'),
        (EVERY_TWO_WEEKS, 'Every two weeks'),
        (MONTHLY, 'Monthly')
    )

    reports_frequency = models.CharField(choices=REPORT_FREQUENCY, default=DAILY, max_length=15)
    survey_reports_frequency = models.CharField(choices=REPORT_FREQUENCY, default=DAILY, max_length=15)

    class Meta:
        abstract = True


def count_subquery(model, field, period, extra_filter=None):
    filters_list = [Q(merchant=OuterRef('pk')),
                    Q(**{field + '__gte': period['from']}),
                    Q(**{field + '__lte': period['to']})]
    if extra_filter:
        filters_list.append(extra_filter)

    qs = model.objects.filter(reduce(operator.and_, filters_list)).values('merchant'). \
        annotate(Count('pk')).values('pk__count')
    return Coalesce(Subquery(qs, output_field=IntegerField()), 0)


def get_used_countries_from_set(merchant, countries_set):
    used_countries = []
    member_phones = merchant.member_set.values_list('phone', flat=True)
    customer_phones = merchant.customer_set.values_list('phone', flat=True)
    subbranding_phones = merchant.subbrandings.values_list('phone', flat=True)
    initiators = merchant.member_set(manager='managers')
    invitation_phones = []
    for initiator in initiators.all():
        invitation_phones += initiator.invitations.values_list('phone', flat=True)
    for phone in set(list(member_phones) + list(subbranding_phones) + list(invitation_phones) + list(customer_phones)):
        for country in countries_set:
            try:
                is_valid = phone_is_valid(phone, [country, ])
            except ValidationError:
                is_valid = False
            if is_valid:
                used_countries.append(country)
                countries_set.remove(country)
                break
        if len(countries_set) == 0:
            break
    countries_names = [name for (abbr, name) in countries if abbr in used_countries]
    return countries_names
