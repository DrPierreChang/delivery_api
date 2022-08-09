from django.contrib.auth import get_user_model

from django_filters.rest_framework import FilterSet

from base.models import Member
from merchant.models import SkillSet
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter


class DriverFilterSet(FilterSet):
    # ?id=5&id=3
    id = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Member.drivers.all())
    # ?skill_sets=171
    skill_sets = RadaroModelMultipleChoiceFilter(
        to_field_name='id',
        queryset=SkillSet.objects.all(),
        conjoined=True,
    )

    class Meta:
        model = get_user_model()
        fields = ['id', 'skill_sets']
