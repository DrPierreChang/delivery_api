from django.http import Http404

from rest_framework import mixins, viewsets
from rest_framework.generics import get_object_or_404

from base.models import Member
from base.permissions import IsManager
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from schedule.api.mobile.schedule.v1.serializers import MobileScheduleSerializer
from schedule.api.mobile.schedule_calendar.v1.serializers import MobileCalendarScheduleSerializer
from schedule.models import Schedule


class ScheduleViewSet(ReadOnlyDBActionsViewSetMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.UpdateModelMixin,
                      viewsets.GenericViewSet):
    queryset = Schedule.objects.all().order_by('id')
    serializer_class = MobileScheduleSerializer
    permission_classes = [UserIsAuthenticated, IsManager]
    lookup_field = 'member_id'

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            member = get_object_or_404(
                Member.drivers.filter(merchant=self.request.user.current_merchant),
                pk=self.kwargs[lookup_url_kwarg],
            )
            return Schedule.objects.create(member=member)

    def get_queryset(self):
        return self.queryset.filter(member_id__in=Member.drivers.filter(merchant=self.request.user.current_merchant))


class ScheduleCalendarViewSet(ReadOnlyDBActionsViewSetMixin,
                              mixins.ListModelMixin,
                              mixins.RetrieveModelMixin,
                              mixins.UpdateModelMixin,
                              viewsets.GenericViewSet):
    queryset = Schedule.objects.all().order_by('id')
    serializer_class = MobileCalendarScheduleSerializer
    permission_classes = [UserIsAuthenticated, IsManager]
    lookup_field = 'member_id'

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            member = get_object_or_404(
                Member.drivers.filter(merchant=self.request.user.current_merchant),
                pk=self.kwargs[lookup_url_kwarg],
            )
            return Schedule.objects.create(member=member)

    def get_queryset(self):
        return self.queryset.filter(member_id__in=Member.drivers.filter(merchant=self.request.user.current_merchant))
