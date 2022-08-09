from django.db.models import Q
from django.http import Http404

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_202_ACCEPTED
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.models import Member
from base.permissions import IsReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from driver.api.legacy.serializers.driver import MerchantsDriverSerializer
from merchant.api.legacy.serializers import (
    ExternalHubSerializer,
    ExternalSkillSetSerializer,
    LabelSerializer,
    SubBrandingSerializer,
)
from merchant.models import Hub, Label, Merchant, SkillSet, SubBranding
from merchant.permissions import IsNotBlocked
from merchant_extension.api.legacy.serializers.core import ExternalChecklistSerializer
from radaro_utils.permissions import IsAdminOrManager
from reporting.decorators import log_fields_on_object
from reporting.mixins import TrackableDestroyModelMixin, TrackableUpdateModelMixin
from route_optimisation.models import RouteOptimisation
from tasks.api.legacy.serializers.core import BulkDelayedUploadSerializer
from tasks.api.legacy.serializers.terminate_code import ExternalTerminateCodeExtendedSerializer
from tasks.api.legacy.views import UploadDelayedTaskViewSet
from tasks.celery_tasks.bulk import bulk__create_jobs
from tasks.celery_tasks.csv import confirm_bulk_upload_v2, generate_orders_from_csv_v2
from tasks.models import BulkDelayedUpload, Order
from tasks.models.terminate_code import TerminateCode
from webhooks.api.permissions import (
    ExternalIsNotBlocked,
    ExternalLabelsEnabled,
    ExternalRouteOptimisationAvailable,
    ExternalSkillSetsEnabled,
)
from webhooks.filters import OrderFilterSet
from webhooks.mixins import MerchantAPIKeyMixin
from webhooks.models import MerchantAPIKey
from webhooks.serializers import (
    APIKeySerializer,
    ExternalOrderPrototypeChunkSerializer,
    ExternalRouteOptimisationSerializer,
    OrderFromExternalJobSerializer,
)


class MerchantAPIKeyViewSet(MerchantAPIKeyMixin, viewsets.GenericViewSet):

    def get_queryset(self):
        merchants = self.merchant_api_key.related_merchants
        return super().get_queryset().filter(merchant_id__in=merchants)


class MerchantAPIKeyAPIView(MerchantAPIKeyMixin, APIView):
    pass


class WebhooksViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, TrackableUpdateModelMixin,
                      TrackableDestroyModelMixin, mixins.ListModelMixin,
                      mixins.CreateModelMixin, MerchantAPIKeyViewSet):
    queryset = Order.objects.all().order_by('-created_at')
    permission_classes = [ExternalIsNotBlocked, ]
    serializer_class = OrderFromExternalJobSerializer
    bulk_serializer_class = ExternalOrderPrototypeChunkSerializer
    lookup_field = 'external_job__external_id'
    additional_lookup_fields = ['order_id', ]
    lookup_url_kwarg = 'pk'
    lookup_value_regex = r'[\w.\-\~]+'
    prefetch_related_list = ('order_confirmation_photos', 'pre_confirmation_photos',
                             'skill_sets', 'labels', 'terminate_codes', 'barcodes',
                             'deliver_address', 'pickup_address', 'starting_point',
                             'driver_checklist__confirmation_photos',
                             'wayback_point', 'wayback_hub__location', 'route_points')
    select_related_list = ('external_job', 'driver', 'manager', 'customer', 'merchant')

    filter_backends = (DjangoFilterBackend,)
    filterset_class = OrderFilterSet

    def __init__(self, *args, **kwargs):
        super(WebhooksViewSet, self).__init__(*args, **kwargs)

    def get_serializer_class(self):
        if self.action == 'create':
            return self.bulk_serializer_class
        else:
            return self.serializer_class

    def get_object(self):
        url_lookup_field = self.request.query_params.get('lookup_field', None)
        if url_lookup_field in self.additional_lookup_fields:
            self.lookup_field = url_lookup_field
        try:
            return super(WebhooksViewSet, self).get_object()
        except Order.MultipleObjectsReturned:
            error_msg = 'More than 1 job found with this ID. In order to {} information about ' \
                        'the necessary job, please make the request with the api key ' \
                        'with which the job was created.'.format(self.action.replace('_', ' '))
            raise ValidationError(error_msg)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        bulk = serializer.validate_and_save()
        bulk__create_jobs(bulk, async_=True, set_confirmation=True)

    def get_queryset(self):
        qs = super(WebhooksViewSet, self).get_queryset()
        if not self.merchant_api_key.is_master_key:
            qs = qs.filter(external_job__source_id=self.merchant_api_key.pk,
                           external_job__source_type__model='merchantapikey')
        return qs.prefetch_related(*self.prefetch_related_list).select_related(*self.select_related_list)

    @action(methods=['patch', 'put', 'post'], detail=True)
    @log_fields_on_object(fields=['status', 'driver'])
    def assign(self, request, **kwargs):
        instance = self.get_object()
        data = {'driver': request.data.get('driver'), 'status': Order.ASSIGNED}
        serializer = self.serializer_class(instance=instance, data=data,
                                           context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)

    @action(methods=['patch', 'put', 'post'], detail=True)
    @log_fields_on_object(fields=['status', 'driver'])
    def unassign(self, request, **kwargs):
        instance = self.get_object()
        data = {'status': Order.NOT_ASSIGNED}
        serializer = self.serializer_class(instance=instance, data=data,
                                           context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)

    @action(methods=['patch', 'put', 'post'], detail=True, permission_classes=[AllowAny, ])
    @log_fields_on_object(fields=['status'])
    def terminate(self, request, **kwargs):
        instance = self.get_object()
        data = {'status': Order.FAILED}
        serializer = self.serializer_class(instance=instance, data=data,
                                           context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        in_process_statuses = [Order.PICK_UP, Order.PICKED_UP, Order.IN_PROGRESS, Order.WAY_BACK]
        if instance.status in in_process_statuses:
            raise serializers.ValidationError(f'You cannot delete job in statuses: {", ".join(in_process_statuses)}')
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.safe_delete()


class ExternalDriversViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                             MerchantAPIKeyViewSet):
    queryset = Member.drivers.all().order_by('-pk')
    serializer_class = MerchantsDriverSerializer

    lookup_field = 'member_id'

    # This method used for supporting API calls by 'id'.
    # In future, for deny access for API calls with 'id', remove it.
    def get_object(self):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        lookup_value = int(self.kwargs[self.lookup_field])
        drivers = queryset.filter(Q(member_id=lookup_value) | Q(id=lookup_value))
        if drivers:
            return drivers.first()
        else:
            raise Http404('No %s matches the given query.' % queryset.model._meta.object_name)

    @action(methods=['get', ], detail=False)
    def search(self, request, *args, **kwargs):
        last_name = request.query_params.get('last_name', '')
        first_name = request.query_params.get('first_name', '')
        try:
            driver = self.get_queryset().get(last_name__icontains=last_name, first_name__icontains=first_name)
        except Member.DoesNotExist:
            raise Http404('No drivers matches the given query.')
        except Member.MultipleObjectsReturned:
            raise ValidationError('There are more than one driver matches the given query.')
        return Response(self.serializer_class(driver).data)


class ExternalSubBrandingViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                                 MerchantAPIKeyViewSet):
    queryset = SubBranding.objects.all()
    serializer_class = SubBrandingSerializer


class ExternalCSVUploadViewSet(ReadOnlyDBActionsViewSetMixin, MerchantAPIKeyViewSet, UploadDelayedTaskViewSet):
    queryset = BulkDelayedUpload.objects.all()
    serializer_class = BulkDelayedUploadSerializer
    method = BulkDelayedUpload.API

    def create(self, request, *args, **kwargs):
        bulk, csv_file = self.create_task()
        if bulk.is_in(BulkDelayedUpload.CREATED):
            bulk.begin()
            bulk.ready()
            bulk.save()
            (generate_orders_from_csv_v2.si(bulk.id, request.auth, 0) | confirm_bulk_upload_v2.si(bulk.id)).delay()
            serializer = self.get_serializer(bulk)
            return Response(data=serializer.data, status=HTTP_202_ACCEPTED)
        else:
            raise Exception('Bulk is not in CREATED state.')

    def _create_bulk_upload(self):
        task = self.queryset.create(creator=self.request.user,
                                    merchant=self.merchant_api_key.merchant,
                                    method=self.method)
        return task


class ExternalLabelViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                           MerchantAPIKeyViewSet):
    queryset = Label.objects.all().select_related('merchant')
    serializer_class = LabelSerializer
    permission_classes = [ExternalLabelsEnabled, ExternalIsNotBlocked]

    def get_queryset(self):
        # cut off irrelevant objects when using multi-key
        qs = super().get_queryset()
        return qs.filter(merchant__enable_labels=True)


class ExternalHubViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                         MerchantAPIKeyViewSet):
    queryset = Hub.objects.all().order_by('id')
    serializer_class = ExternalHubSerializer


class ExternalSkillSetViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              MerchantAPIKeyViewSet):
    queryset = SkillSet.objects.all().select_related('merchant')
    serializer_class = ExternalSkillSetSerializer
    permission_classes = [ExternalSkillSetsEnabled, ExternalIsNotBlocked]

    def get_queryset(self):
        # cut off irrelevant objects when using multi-key
        qs = super().get_queryset()
        return qs.filter(merchant__enable_skill_sets=True)


class ExternalRouteOptimizationViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                                       mixins.CreateModelMixin, MerchantAPIKeyViewSet):
    queryset = RouteOptimisation.objects.all().order_by('-id')
    serializer_class = ExternalRouteOptimisationSerializer
    permission_classes = [ExternalRouteOptimisationAvailable, IsNotBlocked]


class ExternalCompletionCodeViewSet(ReadOnlyDBActionsViewSetMixin, mixins.ListModelMixin, MerchantAPIKeyViewSet):
    queryset = TerminateCode.objects.all()
    serializer_class = ExternalTerminateCodeExtendedSerializer


class ExternalChecklistAPIView(MerchantAPIKeyAPIView):
    permission_classes = [AllowAny, ]

    def get(self, request, *args, **kwargs):
        merchants = [self.merchant_api_key.merchant_id, ] if self.merchant_api_key.key_type == MerchantAPIKey.SINGLE \
            else self.merchant_api_key.merchants.values_list('id', flat=True)
        instances = [(merchant.id, merchant.checklist) for merchant in
                     Merchant.objects.filter(id__in=merchants, checklist_id__isnull=False).select_related('checklist')]
        for merchant_id, checklist in instances:
            setattr(checklist, 'merchant_id', merchant_id)
        serializer = ExternalChecklistSerializer(instance=[checklist for _, checklist in instances], many=True)
        return Response(serializer.data)


class APIKeyViewSet(ReadOnlyDBActionsViewSetMixin, mixins.DestroyModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, mixins.ListModelMixin,
                    viewsets.GenericViewSet):
    queryset = MerchantAPIKey.objects.all().order_by('-pk')
    serializer_class = APIKeySerializer
    permission_classes = [UserIsAuthenticated, Or(IsAdminOrManager, IsReadOnly), IsNotBlocked]
    lookup_field = 'key'

    def get_queryset(self):
        return self.queryset.filter(creator__merchant_id=self.request.user.current_merchant_id,
                                    key_type=MerchantAPIKey.SINGLE)

    def perform_create(self, serializer):
        user = self.request.user
        return serializer.save(creator=user, merchant_id=user.current_merchant_id)
