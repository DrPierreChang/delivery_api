from base.models import Member
from radaro_utils.filters.related_objects_filter import BaseRelatedOnlyFieldListFilter


class BaseManagerOnlyListFilter(BaseRelatedOnlyFieldListFilter):
    qs = Member.managers.all()


class BaseDriverOnlyListFilter(BaseRelatedOnlyFieldListFilter):
    qs = Member.all_drivers.all().not_deleted()


class ManagerOnlyListFilter(BaseManagerOnlyListFilter):
    title = 'Manager'
    parameter_name = 'manager__id'
