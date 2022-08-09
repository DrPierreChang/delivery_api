from django.http import Http404

from rest_framework import mixins, viewsets

from base.models import Member
from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from schedule.models import Schedule

from .serializers import MobileScheduleSerializer


class ScheduleViewSet(ReadOnlyDBActionsViewSetMixin,
                      mixins.RetrieveModelMixin,
                      mixins.UpdateModelMixin,
                      viewsets.GenericViewSet):
    queryset = Schedule.objects.all().order_by('id')
    serializer_class = MobileScheduleSerializer
    permission_classes = [UserIsAuthenticated, IsDriver]
    lookup_field = 'member_id'

    def get_object(self):
        member_id = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        if member_id == 'me':
            member_id = self.request.user.id
        if str(member_id) == str(self.request.user.id):
            schedule, created = Schedule.objects.get_or_create(member_id=member_id)
            return schedule
        raise Http404

    def get_queryset(self):
        return self.queryset.filter(member_id__in=Member.drivers.filter(merchant=self.request.user.current_merchant))
