import json

from django import views
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.mixins import DestroyModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED
from rest_framework.views import APIView

from constance import config
from django_filters.rest_framework import DjangoFilterBackend

from base.models import Car, Invite, Member, SampleFile
from base.permissions import IsAdminOrManagerOrObserver
from base.utils import MobileAppVersionsConstants
from custom_auth.api.legacy.api import UserAuthViewSet
from custom_auth.permissions import UserIsAuthenticated
from driver.api.legacy.serializers.driver import DriverRegisterSerializer
from notification.models import MerchantMessageTemplate
from radaro_utils.permissions import IsAdminOrManager
from radaro_utils.serializers.fields import UTCTimestampField
from reporting.mixins import TrackableCreateModelMixin

from ...utils.views import ReadOnlyDBActionsViewSetMixin
from .serializers import CarSerializer, UserSerializer
from .serializers.delayed import SampleFileSerializer
from .serializers.invitations import InviteSerializer

UserModel = get_user_model()


class EmployeeViewSet(ListModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [UserIsAuthenticated]

    def filter_queryset(self, queryset):
        qs = super(EmployeeViewSet, self).filter_queryset(queryset)
        return qs.filter(merchant=self.request.user.current_merchant)


class ManagerViewSet(ReadOnlyDBActionsViewSetMixin, EmployeeViewSet):
    queryset = Member.managers.all().select_related('merchant')
    merchant_position = Member.MANAGER


class InviteViewSet(ReadOnlyDBActionsViewSetMixin, DestroyModelMixin, ListModelMixin,
                    TrackableCreateModelMixin, viewsets.GenericViewSet):
    serializer_class = InviteSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManager]
    queryset = Invite.objects.all()
    register_serializer = DriverRegisterSerializer

    def perform_create(self, serializer):
        obj = serializer.save(initiator=self.request.user, merchant=self.request.user.current_merchant)
        obj.send_notification(
            template_type=MerchantMessageTemplate.INVITATION,
            merchant_id=obj.initiator.current_merchant_id
        )

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)

    @property
    def new_invites(self):
        return self.queryset.filter(invited__isnull=True)

    @action(methods=['post', 'get'], detail=False, permission_classes=[AllowAny])
    def getcode(self, request, **kwargs):
        serializer = self.register_serializer(
            fields=('phone', 'app_type', 'app_variant'),
            data=request.data,
            query=self.new_invites
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        inv = self.new_invites.get(phone=data['phone'])
        inv.create_driver_pin(sms_android_verification_hash=serializer.get_sms_android_verification_hash())
        return Response(
            data={'detail': 'Pin code was sent to the phone number in invitation.'},
            status=HTTP_200_OK
        )

    @action(methods=['post'], detail=False, permission_classes=[AllowAny])
    def validatecode(self, request, **kwargs):
        serializer = self.register_serializer(data=request.data, fields=('phone', 'pin_code'),
                                              query=self.new_invites)
        serializer.is_valid(raise_exception=True)
        return Response(
            data={'detail': 'Pin code was sent to the phone number in invitation. You may proceed with password.'},
            status=HTTP_200_OK
        )

    @action(methods=['post'], detail=False, permission_classes=[AllowAny])
    def password(self, request, **kwargs):
        serializer = self.register_serializer(data=request.data, fields=('phone', 'pin_code', 'password'),
                                              query=self.new_invites)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data.pop('password')
        instance = self.new_invites.get(phone=serializer.validated_data['phone'])
        new_driver = instance.save_driver(password)
        return Response(data=UserSerializer(instance=new_driver, context={'request': self.request}).data,
                        status=HTTP_201_CREATED,
                        headers={UserAuthViewSet.NEW_TOKEN_HEADER: new_driver.user_auth_tokens.create()})


class ListCars(APIView):
    permission_classes = (UserIsAuthenticated, )

    def get(self, request, **kwargs):
        return Response(Car.vehicle_types_for_version(request.version))


class CarViewSet(ReadOnlyDBActionsViewSetMixin,
                 UpdateModelMixin,
                 RetrieveModelMixin,
                 viewsets.GenericViewSet):
    URL_MAPPING = {
        'get': 'retrieve',
        'put': 'partial_update',
        'patch': 'partial_update',
    }

    permission_classes = (UserIsAuthenticated, )
    serializer_class = CarSerializer

    def get_object(self):
        try:
            return Car.objects.get(member=self.request.user)
        except Car.DoesNotExist:
            raise NotFound('You don\'t have any car.')


class SampleFileViewSet(ReadOnlyDBActionsViewSetMixin, viewsets.ReadOnlyModelViewSet):
    lookup_field = 'category'

    serializer_class = SampleFileSerializer
    queryset = SampleFile.objects.all().order_by(lookup_field)
    permission_classes = (UserIsAuthenticated, IsAdminOrManagerOrObserver)
    filter_backends = (DjangoFilterBackend,)


class TimeView(views.View):
    time = UTCTimestampField(precision=UTCTimestampField.SEC)

    def get(self, request, time, *args, **kwargs):
        server_time = self.time.to_representation(timezone.now())
        try:
            response = {
                'status': 200,
                'content': json.dumps({'time': server_time - float(time or 0)})
            }
        except:
            response = {
                'status': 400,
                'content': json.dumps({'message': 'Malformed url string.'})
            }
        return HttpResponse(**response)


class MobileAppVersionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, app_type, **kwargs):
        if app_type not in MobileAppVersionsConstants.APP_TYPES:
            return Response({'message': 'Wrong app type'}, status=status.HTTP_400_BAD_REQUEST)
        version_config = config.MOBILE_APP_VERSIONS.get(app_type, ['', ''])
        return Response(dict(zip(['current', 'lowest_allowed'], version_config)))
