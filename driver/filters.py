from base.filters import BaseDriverOnlyListFilter


class DriverOnlyListFilter(BaseDriverOnlyListFilter):
    title = 'Driver'
    parameter_name = 'driver__id'


class LocationsMemberOnlyListFilter(BaseDriverOnlyListFilter):
    title = 'Member'
    parameter_name = 'member__id'
