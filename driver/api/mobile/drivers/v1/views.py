from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.utils import translation

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.models import Car, Member
from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import IsSelfOrReadOnly, UserIsAuthenticated
from driver.celery_tasks import stop_active_orders_of_driver
from driver.models import DriverLocation
from driver.utils.locations import prepare_locations_from_serializer
from merchant.models import SkillSet
from merchant.permissions import IsNotBlocked
from reporting.utils.delete import create_delete_event

from .filters import DriverFilterSet
from .serializers import (
    DriverSerializer,
    DriverStatisticSerializer,
    DriverStatusSerializer,
    HistoryMobileDriverLocationSerializer,
    ImageDriverSerializer,
    ListDriverSerializer,
    MobileDriverLocationSerializer,
)


class DriverViewSet(
    ReadOnlyDBActionsViewSetMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, IsSelfOrReadOnly]
    serializer_class = DriverSerializer
    list_serializer_class = ListDriverSerializer
    queryset = Member.drivers.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DriverFilterSet

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant).prefetch_related(
            Prefetch('skill_sets', queryset=SkillSet.objects.all().only('id'))
        )

    def get_object(self):
        if self.kwargs[self.lookup_field] == 'me':
            self.kwargs[self.lookup_field] = self.request.user.id

        return super().get_object()

    def get_serializer_class(self):
        if self.action == 'list':
            return self.list_serializer_class

        if str(self.kwargs[self.lookup_field]) in ['me', str(self.request.user.id)]:
            return self.serializer_class

        return self.list_serializer_class

    def perform_update(self, serializer):
        # return api response in updated user language
        new_language = serializer.validated_data.get('language')
        if new_language:
            translation.activate(new_language)
            self.request.LANGUAGE_CODE = translation.get_language()
        return super().perform_update(serializer)

    @action(detail=True, methods=['patch'])
    def upload_images(self, request, *args, **kwargs):
        instance = self.get_object()

        serializer = ImageDriverSerializer(instance, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(self.get_serializer(instance).data)

    @action(detail=False, methods=['get'])
    def vehicle_types(self, request, *args, **kwargs):
        vehicle_types = [
            {'type': type_key, 'type_name': type_name}
            for type_key, type_name in Car.vehicle_types_for_version(version=2).items()
        ]
        return Response({
            'count': len(vehicle_types),
            'next': None,
            'previous': None,
            'results': vehicle_types
        })

    @action(detail=True, methods=['get'])
    def statistics(self, request, *args, **kwargs):
        return Response(DriverStatisticSerializer(self.get_object(), context={'request': request}).data)

    @action(detail=True, methods=['get', 'put', 'patch'])
    def status(self, request, *args, **kwargs):
        instance = self.get_object()

        if self.request.method == 'GET':
            return Response(data={'work_status': instance.work_status})

        serializer = DriverStatusSerializer(instance, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=self.get_serializer(instance, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def ping(self, request, **kwargs):
        instance = self.get_object()
        instance.set_last_ping()
        return Response()

    @action(detail=True, methods=['post'])
    def locations(self, request, **kwargs):
        driver = self.get_object()
        last_location = DriverLocation.objects.all().filter(member=driver).order_by('-created_at').first()

        if isinstance(request.data, dict) and 'offline_history' in request.data.keys():
            serializer = HistoryMobileDriverLocationSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            prepare_locations_from_serializer(
                serializer, last_location, True, serializer.validated_data['offline_history'],
            )
        else:
            serializer = MobileDriverLocationSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            prepare_locations_from_serializer(serializer, last_location, False)

        driver.set_last_ping()

        return Response(status=status.HTTP_201_CREATED)

    @action(detail=True, url_path='work-status')
    def work_status(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(data={'work_status': instance.work_status})

    def perform_destroy(self, instance):
        create_delete_event(self, instance, instance)
        instance.safe_delete()

        callback = lambda: stop_active_orders_of_driver.delay(instance.id)
        callback() if settings.TESTING_MODE else transaction.on_commit(callback)
