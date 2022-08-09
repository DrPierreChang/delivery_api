import django_filters

from tasks.models import TerminateCode


class TerminateCodeFilterSet(django_filters.FilterSet):
    type = django_filters.ChoiceFilter(choices=TerminateCode.TYPE_CHOICES)

    class Meta:
        model = TerminateCode
        fields = ['type']
