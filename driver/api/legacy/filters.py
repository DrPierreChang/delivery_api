from django.core.exceptions import FieldError

from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import BooleanFilter, ChoiceFilter, FilterSet

from base.models import Member
from driver.utils.drivers import DRIVER_STATUSES_ORDERING_MAP_REVERSED
from merchant.models import SkillSet
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter


class IsOnlineDriverFilter(BooleanFilter):

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        return qs.filter_by_is_online_for_manager(value)


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


class DriverIdFilter(RadaroModelMultipleChoiceFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, queryset=Member.all_objects.all().drivers().deleted_or_active(), **kwargs)

    def filter(self, qs, value):
        qs = super().filter(qs, value)
        action = self.parent.request.parser_context['view'].action
        if action in ['retrieve', 'driver_statistics']:
            return qs.deleted_or_active()

        if action == 'list' and bool(value):
            return qs.deleted_or_active()

        return qs.not_deleted().active()


class DriverFilterSet(FilterSet):
    id = DriverIdFilter(to_field_name='id')
    skill_sets = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=SkillSet.objects.all(), conjoined=True)
    is_online = IsOnlineDriverFilter()
    work_status = WorkStatusDriverFilter()
    status = StatusDriverFilter()

    class Meta:
        model = Member
        fields = ['work_status', 'id', 'skill_sets', 'is_online', 'status', 'deleted']
