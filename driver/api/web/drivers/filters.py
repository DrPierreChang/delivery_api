from django.core.exceptions import FieldError

from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import ChoiceFilter, FilterSet

from base.models import Member
from driver.utils.drivers import DRIVER_STATUSES_ORDERING_MAP_REVERSED
from merchant.models import SkillSet
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter


class WorkStatusDriverFilter(ChoiceFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, choices=Member.work_status_choices, **kwargs)

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        return qs.filter_by_work_status_for_manager(value)


class StatusDriverFilter(ChoiceFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, choices=tuple(DRIVER_STATUSES_ORDERING_MAP_REVERSED.items()), **kwargs)

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        try:
            return qs.filter(_status=value)
        except FieldError:
            return qs


class WebDriverFilterSet(FilterSet):
    id = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Member.drivers.all())
    skill_sets = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=SkillSet.objects.all(), conjoined=True)
    work_status = WorkStatusDriverFilter()
    status = StatusDriverFilter()

    class Meta:
        model = Member
        fields = ['id', 'skill_sets', 'work_status', 'status', 'deleted']


__all__ = ['WebDriverFilterSet']
