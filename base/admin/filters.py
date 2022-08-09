from base.filters import BaseManagerOnlyListFilter
from radaro_utils.filters.date_filters import DateTimeDescFilter


class InitiatorOnlyListFilter(BaseManagerOnlyListFilter):
    title = 'Initiator'
    parameter_name = 'initiator__id'


class LastPingDateFilter(DateTimeDescFilter):
    title = 'Last ping term'
    parameter_name = 'last_ping'
    filtering_lookup = 'last_ping__gte'
    alias_for_lookup = 'Last ping'
