from django.contrib.auth import get_user_model
from django.db.transaction import atomic

from rest_framework import decorators, mixins, permissions, status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from rest_condition import And, Not, Or

from base import signal_senders
from base.api.legacy.serializers import SubManagerUserSerializer, UserSerializer
from base.api.legacy.serializers.members import ManagerSerializer, ObserverSerializer
from base.api.web.manager.serializers import GroupManagerSerializer
from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver, IsGroupManager, IsReadOnly, IsSubManager
from base.signals import logout_event
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import IsSelf, POSTOnlyIfAnonymous, UserIsAuthenticated
from custom_auth.saml2.views import saml_login
from driver.api.legacy.serializers.driver import DriverSerializer
from merchant.api.legacy.serializers import MerchantSerializer
from merchant.models import Merchant
from reporting.mixins import TrackableUpdateModelMixin

from ..mixins import ResetPasswordViewMixin, RetrieveSelfMixin
from .serializers import UsernameLoginSerializer


class UserViewSet(ReadOnlyDBActionsViewSetMixin,
                  RetrieveSelfMixin,
                  ResetPasswordViewMixin,
                  mixins.RetrieveModelMixin,
                  TrackableUpdateModelMixin,
                  mixins.CreateModelMixin,
                  viewsets.GenericViewSet):
    queryset = get_user_model().objects
    permission_classes = [Or(IsReadOnly, And(IsSelf, Not(Or(IsSubManager, IsGroupManager)))), POSTOnlyIfAnonymous]
    merchant_position = Member.ADMIN

    def update(self, request, *args, **kwargs):
        kwargs.update({'partial': True})
        return super(UserViewSet, self).update(request, *args, **kwargs)

    def get_serializer_class(self):
        user = self.request.user
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        is_driver = not user.is_anonymous and user.is_driver
        is_admin_or_manager = not user.is_anonymous and (user.is_admin or user.is_manager)
        is_submanager = not user.is_anonymous and user.is_submanager
        is_group_manager = not user.is_anonymous and user.is_group_manager
        is_observer = not user.is_anonymous and user.is_observer
        is_self = self.kwargs.get(lookup_url_kwarg) == 'me'

        if is_self:
            if is_driver:
                return DriverSerializer
            if is_admin_or_manager:
                return ManagerSerializer
            if is_submanager:
                return SubManagerUserSerializer
            if is_group_manager:
                return GroupManagerSerializer
            if is_observer:
                return ObserverSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        response = super(UserViewSet, self).create(request, *args, **kwargs)
        response.data = None
        return response

    def perform_create(self, serializer):
        obj = serializer.save()
        obj.set_merchant_position(self.merchant_position)


class AvailableMerchantsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):

    queryset = Merchant.objects.all()
    serializer_class = MerchantSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver, IsSelf]

    def get_queryset(self):
        uid = self.kwargs['users_pk']
        if uid == 'me':
            user = self.request.user
        else:
            user = get_object_or_404(get_user_model(), pk=uid)
        self.check_object_permissions(self.request, user)

        return user.merchants.all()


class UserAuthViewSet(viewsets.ViewSet):
    NEW_TOKEN_HEADER = 'X-Token'

    login_serializer_class = UsernameLoginSerializer

    @atomic
    def _basic_login(self, roles, is_force=False, device_id=None):
        serializer = self.get_login_serializer()
        serializer.is_valid(raise_exception=True)
        self.user = serializer.authenticate(roles, is_force)
        if is_force:
            self.user.on_force_login(device_id)
        resp_serializer = self.get_response_serializer(self.user, roles, context={'request': self.request})
        return Response(status=status.HTTP_201_CREATED, headers=self.get_success_headers(), data=resp_serializer.data)

    @decorators.action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny], url_path='login-driver')
    @saml_login(roles=('is_driver', ))
    def login_driver(self, request, roles, **kwargs):
        is_force = request.query_params.get('force', False)
        device_id = request.query_params.get('device_id', None)
        return self._basic_login(roles, is_force=is_force, device_id=device_id)

    # For temporary compatibility with mobile app
    @decorators.action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny], url_path='login')
    def login(self, request, roles=('is_driver', ), **kwargs):
        is_force = request.query_params.get('force', False)
        device_id = request.query_params.get('device_id', None)
        return self._basic_login(roles, is_force=is_force, device_id=device_id)

    @decorators.action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny], url_path='login-merchant')
    @saml_login(roles=('is_admin', 'is_manager', 'is_observer', 'is_submanager', 'is_group_manager'))
    def login_merchant(self, request, roles, **kwargs):
        return self._basic_login(roles)

    def get_login_serializer(self, **kwargs):
        return self.login_serializer_class(data=self.request.data, **kwargs)

    def get_success_headers(self):
        return {self.NEW_TOKEN_HEADER: self.user.user_auth_tokens.create()}

    def get_response_serializer(self, user, roles, **kwargs):
        if 'is_driver' in roles:
            serializer_class = DriverSerializer
        elif user.is_submanager:
            serializer_class = SubManagerUserSerializer
        else:
            serializer_class = UserSerializer

        return serializer_class(instance=user, **kwargs)

    @decorators.action(methods=['delete'], detail=False, permission_classes=[permissions.IsAuthenticated], url_path='logout')
    def logout(self, request, **kwargs):
        auth_token = request._request.META.get('HTTP_AUTHORIZATION', '').split(' ')[-1]

        # TODO: Remove all tokens for drivers on logout. But we must also remove tokens for managers.
        # we do not rely on .is_driver condition since the actual role can be .is_driver_or_manager
        if request.user.role == Member.DRIVER:
            tokens_for_delete = request.user.user_auth_tokens.all()
        else:
            tokens_for_delete = request.user.user_auth_tokens.filter(key=auth_token)
        tokens_for_delete.delete()

        logout_event.send(sender=signal_senders.senders[request.user.current_role], user=request.user)
        return Response(None, status=status.HTTP_204_NO_CONTENT)
