from django.db.models import Count

from rest_framework.decorators import action
from rest_framework.response import Response

from base.permissions import IsAdminOrManagerOrObserver
from custom_auth.permissions import UserIsAuthenticated
from tasks.mixins.order_status import OrderStatus


class CountViewMixin(object):
    status_fieldname_to_count = 'status'

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def count_items(self, request, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        data = queryset.values(self.status_fieldname_to_count).annotate(count=Count(self.status_fieldname_to_count))
        count_items = {obj[self.status_fieldname_to_count]: obj['count'] for obj in data}
        count_items['active'] = sum(count_items.get(status, 0) for status in OrderStatus.status_groups.ACTIVE)
        return Response(data=count_items)
