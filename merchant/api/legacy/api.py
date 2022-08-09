from distutils.util import strtobool

from django.db.models import ProtectedError, Q
from django.http import Http404

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from constance import config
from django_filters.rest_framework import DjangoFilterBackend
from pinax.stripe.actions import customers
from pinax.stripe.models import Card
from rest_condition import Or
from rest_framework_bulk import mixins as bulk_mixins
from watson import search as watson
from watson.models import SearchEntry

from base.models import Member
from base.permissions import IsAdmin, IsAdminOrManagerOrObserver, IsManagerOrReadOnly, IsReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from driver.api.legacy.serializers.driver import DriverInfoSerializer, RelativeDriverSerializer
from merchant.models import Hub, Label, Merchant, SkillSet, SubBranding
from merchant.permissions import IsNotBlocked, LabelsEnabled, SkillSetsEnabled
from merchant.push_messages.composers import SkillSetAddedPushMessage, SkillSetRemovedPushMessage
from merchant.utils import CardPaginationClass
from radaro_utils.permissions import IsAdminOrManager
from reporting.context_managers import track_fields_on_change
from reporting.mixins import TrackableCreateModelMixin, TrackableDestroyModelMixin, TrackableUpdateModelMixin
from tasks.api.legacy.serializers.core import BaseCustomerAddressSerializer
from tasks.models import BulkDelayedUpload, Customer

from .filters import CustomerFilterSet
from .serializers import (
    CardSerializer,
    ChargeSerializer,
    CreateCardSerializer,
    LabelHexSerializer,
    LabelSerializer,
    MerchantSerializer,
    SkillSetSerializer,
    SubBrandingSerializer,
)
from .serializers.hubs import HubSerializer, HubSerializerV2
from .serializers.search import SearchSerializer


class MerchantViewSet(DestroyModelMixin, TrackableUpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = MerchantSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManager]
    queryset = Merchant.objects.all()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'my':
            try:
                return Merchant.objects.get(member=self.request.user)
            except Merchant.DoesNotExist:
                merchant = Merchant.objects.create()
                merchant.member_set.add(self.request.user)
                return merchant
        else:
            raise Http404('Not found.')

    @action(detail=True)
    def balance(self, request, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(data={"balance": serializer.data['balance']})


class SearchAPI(ReadOnlyDBActionsViewSetMixin, ListAPIView):
    serializer_class = SearchSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]
    http_method_names = ['get', 'options']

    def get_queryset(self):

        q = self.request.GET.get('q', '')
        if len(q) < 3:
            return []
        merchant = self.request.user.current_merchant

        orders_q = Q(
            Q(orders_search_entries__bulk__isnull=True)
            | Q(orders_search_entries__bulk__status=BulkDelayedUpload.CONFIRMED),
            orders_search_entries__deleted=False,
            orders_search_entries__merchant_id=merchant.id,
        )
        members_q = Q(
            members_search_entries__is_active=True,
            members_search_entries__role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER],
            members_search_entries__merchant_id=merchant.id,
        )
        search_engine = watson.default_search_engine
        search_results = SearchEntry.objects.all().order_by('-pk')
        search_results = search_results.filter(content__icontains=q).filter(engine_slug=search_engine._engine_slug)
        search_results = search_results.filter(orders_q | members_q)
        search_results = search_results.prefetch_related('object', 'content_type')

        return search_results


class CardViewSet(ReadOnlyDBActionsViewSetMixin, RetrieveModelMixin, DestroyModelMixin, UpdateModelMixin,
                  CreateModelMixin, ListModelMixin, viewsets.GenericViewSet):

    queryset = Card.objects.all()
    serializer_class = CardSerializer
    create_serializer_class = CreateCardSerializer
    permission_classes = [UserIsAuthenticated, IsAdmin]
    pagination_class = CardPaginationClass

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return self.create_serializer_class
        else:
            return self.serializer_class

    def get_queryset(self):
        if hasattr(self.request.user, "customer"):
            return self.queryset.filter(customer_id=self.request.user.customer.id).order_by('-created_at')
        return []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(self.serializer_class(instance=obj).data, status=status.HTTP_201_CREATED)

    @action(methods=['post'], detail=True)
    def change(self, request, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        from pinax.stripe.actions.sources import delete_card
        delete_card(request.user.customer, instance.stripe_id)

        return Response(data=self.serializer_class(obj).data, status=status.HTTP_200_OK)

    @action(methods=['delete'], detail=True)
    def delete(self, request, **kwargs):
        instance = self.get_object()

        from pinax.stripe.actions.sources import delete_card
        delete_card(request.user.customer, instance.stripe_id)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post'], detail=True)
    def charge(self, request, **kwargs):
        instance = self.get_object()
        stripe_customer = instance.customer
        if not customers.can_charge(stripe_customer):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        charge_serializer = ChargeSerializer(data=request.data, context={'request': request})
        charge_serializer.is_valid(raise_exception=True)
        charge_serializer.make_charge(instance)
        return Response(status=status.HTTP_200_OK)


class MerchantCustomerViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]
    queryset = Customer.objects.all().order_by('-pk')
    serializer_class = BaseCustomerAddressSerializer

    filter_backends = (DjangoFilterBackend, )
    filterset_class = CustomerFilterSet

    def get_queryset(self):
        queryset = super().get_queryset().filter(merchant=self.request.user.current_merchant)\
            .select_related('last_address')
        return queryset


class MerchantSubBrandingViewSet(ReadOnlyDBActionsViewSetMixin,
                                 TrackableCreateModelMixin,
                                 TrackableUpdateModelMixin,
                                 TrackableDestroyModelMixin,
                                 viewsets.ModelViewSet):
    permission_classes = [UserIsAuthenticated, Or(IsAdminOrManager, IsReadOnly)]
    queryset = SubBranding.objects.all()
    serializer_class = SubBrandingSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['customer_survey']

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)

    def perform_create(self, serializer):
        serializer.save(merchant=self.request.user.current_merchant)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'detail': "You can't remove the subbrand because there are managers associated with it."
            })


class AllowedCountriesList(APIView):
    permission_classes = [UserIsAuthenticated]

    def get(self, request, **kwargs):
        return Response(config.ALLOWED_COUNTRIES)


class HubViewSet(ReadOnlyDBActionsViewSetMixin,
                 mixins.RetrieveModelMixin,
                 TrackableUpdateModelMixin,
                 TrackableDestroyModelMixin,
                 mixins.ListModelMixin,
                 TrackableCreateModelMixin,
                 viewsets.GenericViewSet):
    queryset = Hub.objects.all().order_by('-pk')

    permission_classes = [UserIsAuthenticated, IsManagerOrReadOnly, IsNotBlocked]

    serializer_class = HubSerializer
    serializer_class_v2 = HubSerializerV2

    def get_serializer_class(self):
        if self.request.version >= 2:
            return self.serializer_class_v2
        return self.serializer_class

    def get_queryset(self):
        user = self.request.user
        merchant = user.current_merchant
        q = self.queryset.filter(merchant=merchant)
        return q.select_related('location', 'merchant').distinct()

    def perform_create(self, serializer):
        obj = serializer.save(merchant=self.request.user.current_merchant)

    def get_pages(self, queryset, serializer_class, **kwargs):
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializer_class(page, many=True, **kwargs)
            return self.get_paginated_response(serializer.data)

        serializer = serializer_class(queryset, many=True, **kwargs)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if any([instance.member_starting.exists(), instance.member_ending.exists()]):
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'detail': 'This hub is set as start/end hub for Route optimisation for the driver.'
            })
        return super(HubViewSet, self).destroy(request, *args, **kwargs)


class MerchantLabelsViewSet(ReadOnlyDBActionsViewSetMixin,
                            TrackableUpdateModelMixin,
                            TrackableCreateModelMixin,
                            TrackableDestroyModelMixin,
                            viewsets.ModelViewSet):
    permission_classes = [UserIsAuthenticated, Or(IsAdminOrManager, IsReadOnly), LabelsEnabled]
    queryset = Label.objects.all()

    serializer_class = LabelSerializer
    serializer_class_v2 = LabelHexSerializer

    def get_serializer_class(self):
        if self.request.version >= 2:
            return self.serializer_class_v2
        return self.serializer_class

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)

    def perform_create(self, serializer):
        serializer.save(merchant=self.request.user.current_merchant)

    @action(url_path='available-colors', detail=False)
    def available_colors(self, request, **kwargs):
        selected_colors = self.get_queryset().values_list('color', flat=True)
        available_colors = [item for item in Label.color_choices if item[0] not in selected_colors]
        return Response(data={"available_colors": available_colors})

    @action(detail=False)
    def colors(self, request, **kwargs):
        color_map = Label.get_versioned_colors_map(request)
        return Response(data=color_map)


class MerchantSkillSetsViewSet(ReadOnlyDBActionsViewSetMixin,
                               TrackableUpdateModelMixin,
                               TrackableCreateModelMixin,
                               TrackableDestroyModelMixin,
                               viewsets.ModelViewSet):
    permission_classes = [UserIsAuthenticated,  Or(IsAdminOrManager, IsReadOnly), SkillSetsEnabled]
    queryset = SkillSet.objects.all()
    serializer_class = SkillSetSerializer

    def filter_queryset(self, queryset):
        qs = super(MerchantSkillSetsViewSet, self).filter_queryset(queryset)

        if not self.request.user.is_driver:
            return qs

        driver_skill_sets = self.request.user.skill_sets.values_list('id', flat=True)
        assigned = self.request.query_params.get('assigned', '')
        try:
            bool_assigned = strtobool(assigned)
        except ValueError:
            return qs.exclude(~Q(id__in=driver_skill_sets) & Q(is_secret=True))
        if bool_assigned:
            return qs.filter(id__in=driver_skill_sets)
        return qs.exclude(Q(id__in=driver_skill_sets) | Q(is_secret=True))

    def get_queryset(self):
        qs = super(MerchantSkillSetsViewSet, self).get_queryset()
        return qs.filter(merchant=self.request.user.current_merchant).prefetch_related('drivers')

    def perform_create(self, serializer):
        serializer.save(merchant=self.request.user.current_merchant)

    @action(methods=['GET'], detail=False)
    def colors(self, request, **kwargs):
        return Response(data={"colors": SkillSet.get_colors()})


class MerchantSkillSetDriversViewSet(
        ReadOnlyDBActionsViewSetMixin,
        bulk_mixins.BulkDestroyModelMixin,
        mixins.ListModelMixin,
        mixins.CreateModelMixin,
        viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, Or(IsAdminOrManager, IsReadOnly), SkillSetsEnabled]
    serializer_class = DriverInfoSerializer
    relative_driver_serializer = RelativeDriverSerializer
    parent_lookup_field = 'skill_set_pk'

    def _get_related_object(self):
        qs = SkillSet.objects.filter(merchant=self.request.user.current_merchant)
        return get_object_or_404(qs, pk=self.kwargs.get(self.parent_lookup_field))

    def get_queryset(self):
        skill_set = self._get_related_object()
        return skill_set.drivers.all().order_by('-pk')

    def create(self, request, *args, **kwargs):
        serializer = self.relative_driver_serializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        drivers = serializer.validated_data.get('drivers', [])

        skill_set = self._get_related_object()
        with track_fields_on_change(list(drivers), initiator=self.request.user, sender=Member):
            skill_set.drivers.add(*drivers)

        for driver in drivers:
            driver.send_versioned_push(SkillSetAddedPushMessage(driver, request.user, skill_set))
        serializer = self.get_serializer(drivers, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def bulk_destroy(self, request, *args, **kwargs):
        skill_set = self._get_related_object()
        serializer = self.relative_driver_serializer(
            data=request.data,
            context={'request': request, 'skill_set': skill_set}
        )
        serializer.is_valid(raise_exception=True)
        drivers = serializer.validated_data.get('drivers', [])

        with track_fields_on_change(list(drivers), initiator=self.request.user, sender=Member):
            skill_set.drivers.remove(*drivers)

        for driver in drivers:
            driver.send_versioned_push(SkillSetRemovedPushMessage(driver, request.user, skill_set))

        return Response(status=status.HTTP_204_NO_CONTENT)
