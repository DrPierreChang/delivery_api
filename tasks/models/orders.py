from __future__ import unicode_literals

import binascii
import datetime
import hashlib
import operator
import re
import uuid
from collections import Iterable
from datetime import date
from functools import reduce

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import (
    Avg,
    BooleanField,
    Case,
    CharField,
    Count,
    F,
    FloatField,
    IntegerField,
    Max,
    Prefetch,
    Q,
    Sum,
)
from django.db.models import Value as V
from django.db.models import When
from django.db.models.functions import Coalesce, Concat
from django.db.models.signals import post_save
from django.forms.models import model_to_dict
from django.utils import timezone, translation
from django.utils.dateformat import DateFormat
from django.utils.encoding import force_bytes
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.http import urlsafe_base64_encode
from django.utils.safestring import mark_safe

from rest_framework.fields import empty

from dateutil import parser
from jsonfield import JSONField
from model_utils import FieldTracker
from pg_utils import Seconds

from base.models import Member
from base.signals import post_bulk_create
from base.utils import generate_id, get_upload_path_100x100
from driver.api.legacy.serializers.location import DriverLocationSerializer
from driver.models import DriverLocation
from merchant.image_specs import ThumbnailGenerator
from merchant.models import Hub, Label, Merchant, SkillSet, SubBranding
from merchant.renderers import ScreenTextRenderer
from merchant_extension.models import ResultChecklist, ResultChecklistConfirmationPhoto, SurveyResult
from notification.mixins import MessageTemplateStatus
from notification.models import Device, MerchantMessageTemplate
from notification.utils import date_template_format
from radaro_utils.db import DistanceFunc, RoundFunc
from radaro_utils.files.utils import get_upload_path
from radaro_utils.helpers import DateUTCOffset
from radaro_utils.models import AttachedPhotoBase, ResizeImageMixin
from radaro_utils.radaro_model_utils.mixins import TrackMixin
from radaro_utils.utils import shortcut_link_safe
from reporting.model_mapping import serializer_map
from reporting.models import Event
from reporting.signals import event_created
from route_optimisation.const import RoutePointKind
from tasks.models.functions import (
    UUID,
    ConcatCodesInfo,
    ConcatLabelsInfo,
    ConcatSkillSetsInfo,
    DateTimeToChar,
    FormatDuration,
    SurveyResultsInfo,
)

from ..descriptors import OrderInDriverRouteQueueDescriptor, OrderInQueueDescriptor, OrderRoutePointDescriptor
from ..mixins.order_status import OrderStatus, StatusFilterConditions
from . import SKID
from .bulk import BulkDelayedUpload
from .customers import Customer
from .external import ExternalJob
from .locations import OrderLocation
from .mixins import OrderTimeDistanceMixin


def order_deadline():
    return timezone.localtime(timezone.now()) + timezone.timedelta(hours=3)


class BaseOrderQuerySet(models.QuerySet):
    def order_by_statuses(self, order_finished_equal=False):
        status_ordering = OrderStatus.get_status_ordering(order_finished_equal)

        return self.annotate(sort_rate=Case(
            *(When(status=status, then=index) for status, index in status_ordering.items()),
            output_field=IntegerField()
        )).annotate(sort_rate_inside_statuses=Case(
            When(status__in=OrderStatus.status_groups.UNFINISHED, then=Seconds(F('deliver_before'))),
            When(status__in=OrderStatus.status_groups.FINISHED, then=Seconds(F('updated_at')) * -1),
            default=0,
            output_field=IntegerField()
        )).order_by('sort_rate', 'sort_rate_inside_statuses').distinct('sort_rate', 'sort_rate_inside_statuses', 'id')

    def order_active_orders_for_driver(self):
        qs = self.annotate(status_sort_rate=Case(
            When(
                status__in=[OrderStatus.ASSIGNED, OrderStatus.PICK_UP, OrderStatus.PICKED_UP, OrderStatus.IN_PROGRESS],
                then=1
            ),
            When(status=OrderStatus.WAY_BACK, then=0),
            default=2,
            output_field=IntegerField())
        )
        qs = qs.order_by('status_sort_rate', 'deliver_before', 'id')
        qs = qs.distinct('status_sort_rate', 'deliver_before', 'id')
        return qs

    def order_inside_concatenated(self):
        qs = self.order_by('deliver_before', 'id')
        qs = qs.distinct('deliver_before', 'id')
        return qs


class OrderQuerySet(BaseOrderQuerySet):
    def basic_qs(self):
        return self.filter(
            Q(bulk__isnull=True) | Q(bulk__status=BulkDelayedUpload.CONFIRMED),
            deleted=False,
            is_concatenated_order=False,
        ).select_related('bulk')

    def order_by_distance(self, latitude, longitude):
        distance_calculation = DistanceFunc(latitude, longitude, self.model, Order.deliver_address)
        distance_annotation = Case(
            When(status__in=[OrderStatus.ASSIGNED, OrderStatus.PICK_UP, OrderStatus.IN_PROGRESS],
                 then=distance_calculation),
            default=0.,
            output_field=models.FloatField(),
        )
        return self.basic_qs().annotate(distance=distance_annotation).order_by('distance')

    def orders_with_archived_field(self, days_to_archive=7):
        return self.annotate(archived=Case(
                When(updated_at__lte=timezone.now() - timezone.timedelta(days=days_to_archive),
                     status__in=OrderStatus.status_groups.FINISHED,
                     then=True
                     ),
                default=False,
                output_field=BooleanField()
            ))

    def get_orders_for_upcoming_delivery_remind(self):
        upcoming_delivery_timeout = datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['upcoming_delivery_timeout'])
        task_period = datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period'])
        upper_bound_upcoming_delivery = timezone.now() + upcoming_delivery_timeout
        return self.filter(
            deliver_before__gte=upper_bound_upcoming_delivery,
            deliver_before__lt=upper_bound_upcoming_delivery + task_period,
            merchant__templates__template_type=MerchantMessageTemplate.UPCOMING_DELIVERY,
            merchant__templates__enabled=True
        )

    def dates_for_csv(self):
        return {
            'geofence_entered': 'geofence_entered_at',
            'pickup_geofence_entered': 'pickup_geofence_entered_at',
            'status': 'completed_at'
        }

    def pick_events_for_csv(self):
        map_fields = self.dates_for_csv()
        events_stats = Event.objects.pick_report_related_dates(
            related_fields=map_fields.keys(),
            related_values=OrderStatus.status_groups.FINISHED + ['True'],
            map_fields=map_fields,
            objects=self
        )
        return events_stats

    def pick_survey_results_for_csv(self):
        return SurveyResult.objects.annotate_json_results()\
            .filter(customer_order__in=self).values('customer_order', 'json_results')

    def _annotate_job_type_for_related_fields(self, field_name, relations):
        if not isinstance(relations, Iterable):
            relations = [relations]

        return self.filter(**{'{}__in'.format(field_name): relations}).annotate(
            assigned=Count('id', filter=Q(status=OrderStatus.ASSIGNED), distinct=True),
            active=Count(
                'id', filter=Q(status__in=OrderStatus.status_groups.ACTIVE_DRIVER[1:]), distinct=True
            )
        )

    def annotate_job_type_for_skillsets(self, skill_sets):
        return self._annotate_job_type_for_related_fields('skill_sets', skill_sets)

    def annotate_job_type_for_drivers(self, drivers):
        return self._annotate_job_type_for_related_fields('driver', drivers)

    def prefetch_for_mobile_api(self):
        return self.select_related(
            'customer', 'pickup', 'deliver_address', 'pickup_address', 'driver_checklist', 'sub_branding',
        ).prefetch_related(
            'labels', 'barcodes', 'skill_sets', 'terminate_codes',
            'pick_up_confirmation_photos', 'pre_confirmation_photos', 'order_confirmation_photos',
            'order_confirmation_documents',
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('skids', to_attr='not_deleted_skids', queryset=SKID.objects.exclude(driver_changes=SKID.DELETED)),
            Prefetch(
                'driver_checklist__confirmation_photos',
                queryset=ResultChecklistConfirmationPhoto.objects.only('id')
            ),
        )

    def prefetch_for_web_api(self):
        return self.select_related(
            'starting_point', 'ending_point', 'manager',
            'pickup', 'pickup_address',
            'customer', 'deliver_address',
            'wayback_point', 'wayback_hub__location',
        ).prefetch_related(
            'labels', 'barcodes', 'skill_sets', 'terminate_codes', 'skids',
            'pick_up_confirmation_photos', 'pre_confirmation_photos', 'order_confirmation_photos',
            'order_confirmation_documents__tags', 'merchant',
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
            Prefetch('external_job', queryset=ExternalJob.objects.only('external_id')),
            Prefetch(
                'driver_checklist__confirmation_photos',
                queryset=ResultChecklistConfirmationPhoto.objects.only('id')
            ),
        )


class DeletedOrderManager(models.Manager):
    def get_queryset(self):
        return BaseOrderQuerySet(self.model, using=self._db).filter(is_concatenated_order=False)

    def orders_in_range(self, date_from, date_to):
        return self.get_queryset().filter(created_at__date__range=(date_from, date_to))


class AggregatedOrderQuerySet(BaseOrderQuerySet):

    def filter_concatenated_head(self):
        return self.filter(is_concatenated_order=True)

    def exclude_concatenated_head(self):
        return self.filter(is_concatenated_order=False)

    def exclude_concatenated_child(self):
        return self.filter(concatenated_order__isnull=True)

    def exclude_nested_orders(self):
        return self.filter(
            Q(merchant__enable_concatenated_orders=True, concatenated_order__isnull=True)
            | Q(merchant__enable_concatenated_orders=False, is_concatenated_order=False)
        )

    def get_orders_for_remind(self, lower_bound, upper_bound):
        from . import ConcatenatedOrder
        content_types = ContentType.objects.get_for_models(Order, ConcatenatedOrder, for_concrete_models=False).values()
        status_events_ids = Event.objects.filter(
            content_type__in=content_types,
            field='status',
        ).values_list('object_id', flat=True)

        order_ids = status_events_ids.filter(
            happened_at__gt=lower_bound,
            happened_at__lte=upper_bound,
            new_value__in=[OrderStatus.DELIVERED, OrderStatus.WAY_BACK],
        ).filter(
            object_id__in=status_events_ids.filter(new_value=OrderStatus.IN_PROGRESS),
        ).exclude(
            object_id__in=status_events_ids.filter(new_value=OrderStatus.WAY_BACK, happened_at__lte=lower_bound),
        )

        orders_qs = self.exclude_nested_orders().filter(
            status__in=[OrderStatus.DELIVERED, OrderStatus.WAY_BACK],
            is_confirmed_by_customer=False,
            id__in=order_ids,
        )

        return orders_qs


class AggregatedOrderManager(models.Manager):
    def get_queryset(self):
        return AggregatedOrderQuerySet(self.model, using=self._db).filter(
            Q(bulk__isnull=True) | Q(bulk__status=BulkDelayedUpload.CONFIRMED),
            deleted=False,
        ).select_related('bulk')

    def filter_by_merchant(self, merchant):
        if merchant.enable_concatenated_orders:
            orders = self.get_queryset().exclude_concatenated_child()
        else:
            orders = self.get_queryset().exclude_concatenated_head()

        return orders.filter(merchant=merchant)

    @staticmethod
    def bulk_status_change(order_ids, to_status, driver=None,
                           initiator=None, background_notification=False):
        assert to_status in [OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED]
        if to_status == OrderStatus.ASSIGNED:
            assert driver is not None, 'You should pass driver'
        if to_status == OrderStatus.NOT_ASSIGNED:
            driver = None

        track_fieldnames = ['driver', 'status']
        old_values = {}
        old_orders = {}
        events_for_create = []
        # Evaluate 'order_ids' queryset, because it will be updated soon and will not return any value
        ids = list(order_ids)

        from tasks.models import ConcatenatedOrder
        for order in Order.objects.filter(id__in=ids):
            old_values[order.order_id] = model_to_dict(order, fields=track_fieldnames)
        for order in ConcatenatedOrder.objects.filter(id__in=ids):
            old_values[order.order_id] = model_to_dict(order, fields=track_fieldnames)
            for nested_order in order.orders.all():
                old_values[nested_order.order_id] = model_to_dict(nested_order, fields=track_fieldnames)
            old_orders[order.order_id] = order

        Order.aggregated_objects.filter(id__in=ids).update(driver=driver, status=to_status)

        for order in ConcatenatedOrder.objects.filter(id__in=ids).select_related('merchant'):
            changed_nested_orders = order.nested_orders_save(existed_concatenated_order=old_orders[order.order_id])
            ids = list(set(ids) | {nested_order.id for nested_order in changed_nested_orders})
            for event in AggregatedOrderManager._event_from_bulk(order, initiator, old_values, track_fieldnames):
                events_for_create.append(event)
        for order in Order.objects.filter(id__in=ids).select_related('merchant'):
            for event in AggregatedOrderManager._event_from_bulk(order, initiator, old_values, track_fieldnames):
                events_for_create.append(event)

        created = Event.objects.bulk_create(events_for_create)
        post_bulk_create.send(Event, instances=created, background_notification=background_notification)

    @staticmethod
    def _event_from_bulk(order, initiator, old_values, track_fieldnames):
        common_params = dict(merchant=order.merchant, object=order, initiator=initiator)
        for key in track_fieldnames:
            yield Event(field=key, new_value=getattr(order, key), event=Event.CHANGED, **common_params)
        obj_dump = {
            "new_values": model_to_dict(order, fields=track_fieldnames),
            "old_values": old_values.get(order.order_id)
        }
        yield Event(obj_dump=obj_dump, event=Event.MODEL_CHANGED, **common_params)


class OrderManager(models.Manager):

    def get_queryset(self):
        return OrderQuerySet(self.model, using=self._db).basic_qs()

    def _queryset_by_owner(self, merchant, driver_id):
        queryset = self.get_queryset()
        if merchant:
            queryset = queryset.filter(merchant__in=merchant) if isinstance(merchant, Iterable) \
                else queryset.filter(merchant=merchant)
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        return queryset

    def _by_last_updates(self, merchant, driver_id=None, date_from=None,
                         date_to=None, group=None, sub_branding_id=None,
                         extra_conditions=None):

        conditions_dict = dict(updated_at__gte=date_from, updated_at__lte=date_to)
        if sub_branding_id:
            conditions_dict['sub_branding_id__in'] = [sub_branding_id, ] \
                if not isinstance(sub_branding_id, Iterable) else sub_branding_id
        if group:
            conditions_dict.update(StatusFilterConditions.status_groups[group])

        conditions = Q(**conditions_dict)

        qs = self._queryset_by_owner(merchant, driver_id).filter(conditions)
        return qs if not extra_conditions else qs.filter(extra_conditions)

    @staticmethod
    def group_by_date(queryset, df, merchant_tz):
        utc_offset = df.utcoffset() or '00:00:00'
        queryset = queryset.annotate(
            date=DateUTCOffset(F('updated_at'), str(utc_offset), default_tz=str(merchant_tz))
        )
        return queryset.values('date')

    def sum_report_by_date(self, merchant, **params):
        date_from = params['date_from']

        return self.group_by_date(self._by_last_updates(merchant, **params), date_from, merchant.timezone)\
            .annotate(
            successful_tasks=Sum(
                Case(When(status__in=OrderStatus.status_groups.SUCCESSFUL, then=1),
                     default=0, output_field=IntegerField())
            ),
            unsuccessful_tasks=Sum(
                Case(When(status__in=OrderStatus.status_groups.UNSUCCESSFUL, then=1),
                     default=0, output_field=IntegerField())
            ),
            total_tasks=Sum(
                Case(When(status__in=OrderStatus.status_groups.FINISHED,
                          then=1),
                     default=0, output_field=IntegerField())
            )
        ).order_by('date')

    def detail_report_by_date(self, merchant, **params):
        return self._by_last_updates(merchant, **params).order_by('merchant__id', 'id'). \
                                                        distinct('merchant__id', 'id')

    def report_with_assigned_at_events(self, sort_by='created_at', desc=True, *args, **kwargs):
        order_content_type_id = ContentType.objects.get(model='order', app_label='tasks').id

        sign = '-' if desc else ''
        orders = self._by_last_updates(*args, **kwargs).order_by(sign + sort_by) \
            .distinct(sort_by, 'id').select_related('driver')
        evs = dict(Event.objects.filter(object_id__in=orders, content_type_id=order_content_type_id,
                                        new_value=OrderStatus.ASSIGNED)
                   .values('object_id').annotate(last_assigned=Max('happened_at'))
                   .order_by('-happened_at')
                   .values_list('object_id', 'last_assigned'))
        return orders, evs

    def order_locations_by_date(self, merchant=None, **params):
        params['group'] = StatusFilterConditions.INACTIVE
        return self._by_last_updates(merchant, **params).values_list('deliver_address__location', flat=True)

    def distance_time_by_date(self, merchant, **params):
        date_from = params['date_from']
        params['group'] = StatusFilterConditions.SUCCESSFUL

        return self.group_by_date(self._by_last_updates(merchant, **params), date_from, merchant.timezone) \
            .extra(select={'date': 'DATE("tasks_order"."updated_at")'})\
            .values('date')\
            .annotate(avg_distance=Avg('order_distance') / merchant.distance_show_in,
                      avg_duration=Avg(Seconds('duration'), output_field=FloatField()) / 60.,
                      sum_distance=Sum('order_distance', output_field=FloatField()) / merchant.distance_show_in,
                      sum_duration=Sum(Seconds('duration'), output_field=FloatField()) / 60.,
                      finished_tasks=Count('id')
                      ).order_by('date')

    def create_in_bulk(self, orders):
        # all orders should have same merchant
        merchant = orders[0].merchant
        if merchant.checklist_id:
            driver_checklists = ResultChecklist.objects.bulk_create(
                ResultChecklist(checklist_id=merchant.checklist_id) for _ in orders
            )
            for driver_checklist, instance in zip(driver_checklists, orders):
                instance.driver_checklist = driver_checklist
        created_orders = self.bulk_create(
            [order.prepare_save(existed_order=None) for order in orders]
        )

        balance_decrease = 0
        for order in created_orders:
            balance_decrease -= order.cost

        merchant.change_balance(balance_decrease)
        return created_orders

    def create_in_mixed_bulk(self, orders):
        job_checklists = [ResultChecklist(checklist_id=order.merchant.checklist_id) for order in orders
                          if order.merchant.checklist_id]
        driver_checklists = ResultChecklist.objects.bulk_create(job_checklists)
        for driver_checklist, order in zip(driver_checklists, orders):
            order.driver_checklist = driver_checklist

        created_orders = self.bulk_create(order.prepare_save(existed_order=None) for order in orders)
        for order in created_orders:
            order.merchant.change_balance(-order.cost)

        return created_orders

    def create_bulk_events(self, objs):
        created = Event.objects.bulk_create(
            Event(object=obj, merchant=obj.merchant, event=Event.CREATED,
                  obj_dump=obj.order_dump, initiator=obj.manager) for obj in objs
        )
        post_bulk_create.send(Event, instances=created)
        for event in created:
            post_save.send(Event, instance=event, created=True)
            event_created.send(sender=None, event=event)

    def for_csv(self, merchant, tz=None, date_format=None, **params):
        public_report_url_annotation = Concat(
            V(settings.FRONTEND_URL),
            V('/public-report/'),
            UUID(expression='merchant_id'),
            V('/'), 'order_token',
            V('?domain='), V(settings.CURRENT_HOST),
            V('&cluster_number='), V(settings.CLUSTER_NUMBER.lower()),
            output_field=CharField()
        )
        order_distance_annotation = RoundFunc(Case(
            When(order_distance__isnull=False, merchant__distance_show_in=Merchant.MILES,
                 then=F('order_distance')/Merchant.MILES),
            default=F('order_distance'),
            output_field=FloatField(),
        ), 2)

        survey = params.pop('survey', None)
        qs = self.detail_report_by_date(merchant=merchant, **params) \
            .annotate(
                deliver_after_tz=DateTimeToChar('deliver_after', tz=tz, date_format=date_format),
                deliver_before_tz=DateTimeToChar('deliver_before', tz=tz, date_format=date_format),
                pickup_after_tz=DateTimeToChar('pickup_after', tz=tz, date_format=date_format),
                pickup_before_tz=DateTimeToChar('pickup_before', tz=tz, date_format=date_format),
                created_at_tz=DateTimeToChar('created_at', tz=tz, date_format=date_format),
                started_at_tz=DateTimeToChar('started_at', tz=tz, date_format=date_format),
                completion_codes=ConcatCodesInfo(data_field='code'),
                completion_descriptions=ConcatCodesInfo(data_field='name'),
                formatted_time_at_job=FormatDuration(data_field='time_at_job'),
                formatted_duration=FormatDuration(data_field='duration'),
                formatted_inside_geofence=FormatDuration(data_field='time_inside_geofence'),
                formatted_time_at_pickup=FormatDuration(data_field='time_at_pickup'),
                manager_name=Concat('manager__first_name', V(' '), 'manager__last_name', output_field=CharField()),
                driver_name=Concat('driver__first_name', V(' '), 'driver__last_name', output_field=CharField()),
                full_report_url=Case(When(status__in=OrderStatus.status_groups[OrderStatus.FINISHED],
                                          then=public_report_url_annotation), default=V(''),
                                     output_field=CharField()),
                formatted_labels=ConcatLabelsInfo(data_field='id'),
                label_names=ConcatLabelsInfo(data_field='name'),
                formatted_skill_sets=ConcatSkillSetsInfo(data_field='id'),
                skill_set_names=ConcatSkillSetsInfo(data_field='name'),
                order_distance_calculated=order_distance_annotation,
            )
        if survey:
            qs = qs.filter(customer_survey__checklist=survey) \
                .annotate(
                survey_results=Coalesce(SurveyResultsInfo(), V("{}")),
                survey_passed_at=DateTimeToChar(F('customer_survey__created_at'), tz=tz, date_format=date_format)
            )
        return qs


class Order(OrderTimeDistanceMixin, ResizeImageMixin, OrderStatus, TrackMixin, models.Model):
    in_delivery_time_queue = OrderInQueueDescriptor()
    in_driver_route_queue = OrderInDriverRouteQueueDescriptor()
    order_route_point = OrderRoutePointDescriptor()

    search_entries = GenericRelation(
        'watson.SearchEntry',
        content_type_field='content_type',
        object_id_field='object_id_int',
        related_query_name='orders_search_entries',
    )

    route_points = GenericRelation(
        'route_optimisation.RoutePoint',
        content_type_field='point_content_type',
        object_id_field='point_object_id',
        related_query_name='orders',
    )

    thumbnailer = ThumbnailGenerator({
        'confirmation_signature': 'thumb_confirmation_signature_100x100_field',
        'pre_confirmation_signature': 'thumb_pre_confirmation_signature_100x100_field',
    })
    tracker = FieldTracker()
    track_fields = {'confirmation_signature', 'pre_confirmation_signature'}

    external_job = models.OneToOneField('tasks.ExternalJob', null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name='order')
    model_prototype = models.OneToOneField('tasks.OrderPrototype', null=True, blank=True, on_delete=models.SET_NULL,
                                           related_name='order')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    capacity = models.FloatField(null=True, blank=True, validators=[MinValueValidator(limit_value=0)],
                                 help_text='Float capacity value in local units of measurement')
    comment = models.TextField(blank=True)
    driver = models.ForeignKey('base.Member', null=True, blank=True, on_delete=models.PROTECT)
    actual_device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.SET_NULL,
                                      help_text="Driver's device that have used for work with current order")
    manager = models.ForeignKey('base.Member', related_name='orders', on_delete=models.PROTECT)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='orders')
    sub_branding = models.ForeignKey(SubBranding, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='orders')

    deliver_address = models.ForeignKey(OrderLocation, related_name='deliver', on_delete=models.PROTECT)
    deliver_after = models.DateTimeField(blank=True, null=True)
    deliver_before = models.DateTimeField(default=order_deadline)

    pickup = models.ForeignKey('tasks.Pickup', blank=True, null=True, on_delete=models.PROTECT)
    pickup_address = models.ForeignKey(OrderLocation, related_name='pickup', null=True, blank=True,
                                       on_delete=models.PROTECT)
    pickup_after = models.DateTimeField(blank=True, null=True)
    pickup_before = models.DateTimeField(blank=True, null=True)

    starting_point = models.ForeignKey(OrderLocation, related_name='starting', null=True, blank=True,
                                       on_delete=models.PROTECT)
    ending_point = models.ForeignKey(OrderLocation, related_name='ending', null=True, blank=True,
                                     on_delete=models.PROTECT)
    wayback_point = models.ForeignKey(OrderLocation, related_name='wayback', null=True, blank=True,
                                      on_delete=models.PROTECT)
    wayback_hub = models.ForeignKey(Hub, related_name='wayback', null=True, blank=True,
                                    on_delete=models.PROTECT)
    status = models.CharField(choices=OrderStatus._status, max_length=20, default=OrderStatus.NOT_ASSIGNED)
    customer = models.ForeignKey(Customer, related_name='orders', on_delete=models.PROTECT)
    order_token = models.CharField(max_length=150, blank=True, db_index=True)
    order_id = models.PositiveIntegerField(unique=True, db_index=True)
    confirmation_signature = models.ImageField(null=True, blank=True, upload_to=get_upload_path)
    thumb_confirmation_signature_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                                   upload_to=get_upload_path_100x100)
    confirmation_comment = models.TextField(null=True, blank=True)
    pre_confirmation_signature = models.ImageField(null=True, blank=True, upload_to=get_upload_path,
                                                   verbose_name='Pre-inspection signature')
    thumb_pre_confirmation_signature_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                                       upload_to=get_upload_path_100x100)
    pre_confirmation_comment = models.TextField(null=True, blank=True, verbose_name='Pre-inspection comment')
    pick_up_confirmation_signature = models.ImageField(null=True, blank=True, upload_to=get_upload_path)
    thumb_pick_up_confirmation_signature_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                                           upload_to=get_upload_path_100x100)
    pick_up_confirmation_comment = models.TextField(null=True, blank=True)
    deleted = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    pickup_geofence_entered = models.NullBooleanField(blank=True, null=True)
    time_inside_pickup_geofence = models.DurationField(blank=True, null=True)
    time_at_pickup = models.DurationField(blank=True, null=True)

    geofence_entered = models.NullBooleanField(null=True, blank=True)
    geofence_entered_on_backend = models.NullBooleanField(null=True, blank=True)
    is_completed_by_geofence = models.BooleanField(default=False)
    is_confirmed_by_customer = models.BooleanField(default=False)

    time_inside_geofence = models.DurationField(null=True, blank=True)
    time_at_job = models.DurationField(null=True, blank=True)

    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    customer_comment = models.TextField(null=True, blank=True)

    # For bulk csv upload. Allows front-end to get orders, created with bulk upload and e.g.
    # display how much is created, and how much is failed and so on.
    bulk = models.ForeignKey('BulkDelayedUpload', null=True, blank=True, related_name='orders',
                             on_delete=models.SET_NULL)
    path = JSONField(blank=True, null=True)
    # GPS track with filtered by accuracy
    real_path = JSONField(blank=True, null=True)
    # Serialized original track
    serialized_track = JSONField(default=list, blank=True)
    cost = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    events = GenericRelation(Event, related_query_name='orders', for_concrete_model=False)

    deadline_notified = models.BooleanField(default=False)
    deadline_passed = models.BooleanField(default=False)

    driver_checklist = models.OneToOneField(
        'merchant_extension.ResultChecklist', null=True, blank=True,
        on_delete=models.SET_NULL
    )
    labels = models.ManyToManyField(Label, related_name='orders', blank=True)
    customer_survey = models.OneToOneField(
        'merchant_extension.SurveyResult',
        null=True, blank=True, related_name='customer_order',
        on_delete=models.SET_NULL
    )
    customer_review_opt_in = models.BooleanField(
        default=False, verbose_name='Customer review opt-in'
    )
    skill_sets = models.ManyToManyField(SkillSet, related_name='orders', blank=True)

    changed_in_offline = models.BooleanField(default=False)

    terminate_codes = models.ManyToManyField('TerminateCode', related_name='orders', blank=True)
    terminate_comment = models.TextField(null=True, blank=True)

    deliver_day = models.DateField(null=True, blank=True)
    is_concatenated_order = models.BooleanField(default=False)
    concatenated_order = models.ForeignKey(
        'tasks.ConcatenatedOrder', null=True, blank=True, on_delete=models.SET_NULL, related_name='orders'
    )

    enable_rating_reminder = models.BooleanField(default=True)

    store_url = models.URLField(null=True, blank=True, verbose_name='Custom “URL” redirect link')

    objects = OrderManager()
    all_objects = DeletedOrderManager()
    aggregated_objects = AggregatedOrderManager()

    class Meta:
        indexes = [
            models.Index(
                fields=['deleted', 'status'],
                condition=Q(deleted=False, status__in=[
                    OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP, OrderStatus.WAY_BACK, OrderStatus.ASSIGNED,
                ]),
                name='tasks_order_index_sort_status',
            ),
        ]

    @property
    def in_queue(self):
        return self.in_driver_route_queue['number'] or self.in_delivery_time_queue

    @property
    def thumb_pre_confirmation_signature_100x100(self):
        if self.thumb_pre_confirmation_signature_100x100_field:
            return self.thumb_pre_confirmation_signature_100x100_field
        else:
            return self.pre_confirmation_signature

    @property
    def thumb_confirmation_signature_100x100(self):
        if self.thumb_confirmation_signature_100x100_field:
            return self.thumb_confirmation_signature_100x100_field
        else:
            return self.confirmation_signature

    @property
    def thumb_pick_up_confirmation_signature_100x100(self):
        if self.thumb_pick_up_confirmation_signature_100x100_field:
            return self.thumb_pick_up_confirmation_signature_100x100_field
        else:
            return self.pick_up_confirmation_signature

    def _on_pre_confirmation_signature_change(self, previous):
        if self.pre_confirmation_signature:
            if self.pre_confirmation_signature.height > 200:
                self.resize_image(self.pre_confirmation_signature)
            self.thumbnailer.generate_for('pre_confirmation_signature')

    def _on_confirmation_signature_change(self, previous):
        if self.confirmation_signature:
            if self.confirmation_signature.height > 200:
                self.resize_image(self.confirmation_signature)
            self.thumbnailer.generate_for('confirmation_signature')

    def _on_pick_up_confirmation_signature_change(self, previous):
        if self.pick_up_confirmation_signature:
            if self.pick_up_confirmation_signature.height > 200:
                self.resize_image(self.pick_up_confirmation_signature)
            self.thumbnailer.generate_for('pick_up_confirmation_signature')

    @staticmethod
    def autocomplete_search_fields():
        return "title__icontains", "status__icontains", "order_id__iexact"

    @cached_property
    def locations_cost(self):
        if self.cost is not None:
            from tasks.utils import calculate_locations_cost
            return calculate_locations_cost(self)
        return None

    @cached_property
    def terminate_code(self):
        if not self.pk:
            return
        return self.terminate_codes.first()

    @cached_property
    def label(self):
        if not self.pk:
            return
        return self.labels.first()

    @property
    def is_concatenated_child(self):
        return self.concatenated_order_id is not None

    def set_status(self, status):
        self.status = status
        self.save(update_fields=('status',))

    def assign_driver(self, driver):
        self.driver = driver
        status = self.ASSIGNED
        self.set_status(status)

    @classmethod
    def order_id_comparator(cls, _id):
        return cls.all_objects.filter(order_id=_id).exists()

    @classmethod
    def generate_id(cls):
        return generate_id(length=7, cmpr=cls.order_id_comparator, prefix=1)

    def prepare_save(self, existed_order):
        order = existed_order
        if not order:
            self.cost = self.merchant.price_per_job
        if not self.order_token:
            self.order_token = uuid.uuid4()
        no_order_id = not self.order_id
        if no_order_id:
            self.order_id = self.generate_id()
        if no_order_id or not self.customer.last_address or (order and order.deliver_address != self.deliver_address):
            self.customer.last_address = self.deliver_address
            self.customer.save(update_fields=('last_address',))
        if not self.title:
            title = (self.external_job.external_id if self.external_job_id else '') or 'Job: ID ' + str(self.order_id)
            self.title = title[:255]
        if self.deadline_notified and order and order.deliver_before != self.deliver_before:
            self.deadline_notified = False
        if order and order.status != self.status == OrderStatus.NOT_ASSIGNED:
            self.deadline_notified = False
        if self.description != getattr(order, 'description', ''):
            self.transform_description()
        return self

    def save(self, existed_order=empty, **kwargs):
        if existed_order is empty:
            order = Order.objects.filter(pk=self.pk).first() if self.pk else None
        else:
            order = existed_order
        self.prepare_save(order)
        super(Order, self).save(**kwargs)
        if not order:
            self.remind_about_upcoming_delivery()

    def safe_delete(self):
        self.deleted = True
        self.save(update_fields=['deleted'])
        if self.external_job_id:
            self.external_job.safe_delete()

    def remind_about_upcoming_delivery(self):
        from tasks.celery_tasks.reminder import CACHE_KEY_UPCOMING_DELIVERY
        last_time_task = cache.get(CACHE_KEY_UPCOMING_DELIVERY, timezone.now())
        time_to_deadline = self.deliver_before - timezone.now()
        time_over_timeout = time_to_deadline - timezone.timedelta(
            seconds=settings.CUSTOMER_MESSAGES['upcoming_delivery_timeout'])
        time_to_task = timezone.timedelta(
            seconds=settings.CUSTOMER_MESSAGES['task_period']) - (timezone.now() - last_time_task)
        soon_delivery = time_over_timeout < time_to_task
        if soon_delivery or self.merchant.instant_upcoming_delivery_enabled:
            from tasks.celery_tasks.reminder import remind_about_upcoming_delivery
            callback = lambda: remind_about_upcoming_delivery.delay(order_id=self.order_id)
            callback() if settings.TESTING_MODE else transaction.on_commit(callback)

    def get_message_to_customer(self):
        if self.deliver_after:
            delivery_interval_lower = self.deliver_after
        else:
            delivery_interval_lower = self.deliver_before - datetime.timedelta(hours=self.merchant.delivery_interval)
        delivery_interval_upper = self.deliver_before

        if self.merchant.route_optimization != Merchant.ROUTE_OPTIMIZATION_DISABLED:
            from route_optimisation.models import RouteOptimisation
            ro_route_point = self.route_points.last()
            if ro_route_point and ro_route_point.route.optimisation.state \
                    in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING):
                delivery_interval_lower, delivery_interval_upper = ro_route_point.planned_order_arrival_interval

        delivery_interval_lower = delivery_interval_lower.astimezone(self.merchant.timezone)
        delivery_interval_upper = delivery_interval_upper.astimezone(self.merchant.timezone)

        with translation.override(self.merchant.language):
            delivery_interval = date_format(delivery_interval_lower.time(), 'g:i A')
            delivery_interval += ' - ' + date_format(delivery_interval_upper.time(), 'g:i A')

            if self.merchant.date_format == Merchant.LITTLE_ENDIAN:
                # Europe
                delivery_day = self.deliver_before.astimezone(self.merchant.timezone).date()
                delivery_day_short = date_format(delivery_day, 'j E')
                delivery_day_full = date_format(delivery_day, 'j E Y')
            else:
                # USA
                delivery_day = self.deliver_before.astimezone(self.merchant.timezone).date()
                delivery_day_short = date_format(delivery_day, 'F j')
                delivery_day_full = date_format(delivery_day, 'F j, Y')

        # Must match the data from the ScreenTextRenderer.get_context_example
        context = {
            'delivery_day_short': delivery_day_short,
            'delivery_day_full': delivery_day_full,
            'delivery_interval': delivery_interval,
            'queue': self.in_queue,
            'merchant': self.sub_branding.name if self.sub_branding_id else self.merchant.name,
            'customer_name': self.customer.name,
            'delivery_address': self.deliver_address.address,
        }

        if self.status == self.NOT_ASSIGNED:
            return ScreenTextRenderer(self.merchant.not_assigned_job_screen_text).render(context)
        elif self.status in [self.ASSIGNED, self.PICK_UP, self.PICKED_UP]:
            return ScreenTextRenderer(self.merchant.assigned_job_screen_text).render(context)
        if self.status == self.FAILED:
            return ScreenTextRenderer(self.merchant.job_failure_screen_text).render(context)

        return None

    def get_message_to_pickup(self):
        if self.status == self.FAILED:
            return ScreenTextRenderer(self.merchant.pickup_failure_screen_text).render(context=None)
        return None

    def clean(self):
        if Order.is_driver_required_for(self.status) and not self.driver:
            error_msg = "You can't set order's status to '{status}' without assigning driver."
            raise ValidationError(error_msg.format(status=OrderStatus._status_dict[self.status]))
        elif self.status == self.NOT_ASSIGNED and self.driver:
            raise ValidationError('You must remove driver from the order.')

    def get_order_url(self, delivery_route=True):
        route, observer_id = ('order', self.customer.pk) if delivery_route else ('pickup', self.pickup.pk)
        uid = urlsafe_base64_encode(force_bytes(observer_id))
        query_params = dict(
            domain=settings.CURRENT_HOST,
            merchant_identifier=self.merchant.merchant_identifier,
            cluster_number=settings.CLUSTER_NUMBER.lower(),
            lang=self.merchant.language,
        )
        query_string = '&'.join(map(lambda item: '{}={}'.format(item[0], item[1]), query_params.items()))
        order_url = "{base_url}/{route}/{uidb64}/{order_token}?{args}".format(
            base_url=settings.CUSTOMER_FRONTEND_URL,
            route=route, uidb64=uid, order_token=self.order_token,
            args=query_string,
        )
        if self.merchant.shorten_sms_url and not settings.DEBUG:
            return Order.get_shorten_order_url(order_url)
        return mark_safe(order_url)

    @staticmethod
    def get_shorten_order_url(order_url):
        return shortcut_link_safe(order_url)

    def on_start_statuses(self, change_time, to_status):
        if self.started_at is not None:
            return
        if not self.starting_point:
            location = self.driver.location.last()
            if location:
                self.starting_point = OrderLocation.from_location_object(location)
        self.started_at = change_time
        self._calculate_order_distance(to_status)

    def _calculate_order_distance(self, to_status):
        if self.starting_point is None:
            return
        points = [self.starting_point.location, ]
        if to_status == OrderStatus.PICK_UP:
            points.append(self.pickup_address.location)
        points.append(self.deliver_address.location)
        self._pre_calculate_order_distance(points, to_status)

    def end_order(self):
        if not self.ending_point and self.driver:
            location = self.driver.location.last()
            if location:
                self.ending_point = OrderLocation.from_location_object(location)
        self.save(update_fields=('ending_point',))

    def calculate_wayback_distance(self):
        wayback_dest = self.wayback_point or (self.wayback_hub.location if self.wayback_hub else None)
        points = [self.deliver_address.location, wayback_dest.location] if wayback_dest else None
        self._pre_calculate_wayback_distance(points)

    def set_update_time(self):
        self.updated_at = timezone.now()
        self.save(existed_order=self, update_fields=('updated_at',))

    def set_actual_device(self):
        if not self.driver:
            return
        device = self.driver.device_set.filter(in_use=True).first()
        if not device:
            return
        self.actual_device = device
        self.save(update_fields=('actual_device',))

    @property
    def order_dump(self):
        Serializer = serializer_map.get_for(Order)
        return Serializer(self).data

    @property
    def driver_checklist_passed(self):
        if not self.driver_checklist_id:
            return True
        return self.driver_checklist.is_passed

    @cached_property
    def eta(self):
        from tasks.utils.order_eta import ETAToOrders
        eta = ETAToOrders.get_eta(self)
        return None if eta is None else eta['text']

    @cached_property
    def eta_seconds(self):
        from tasks.utils.order_eta import ETAToOrders
        eta = ETAToOrders.get_eta(self)
        return None if eta is None else eta['value']

    def allow_order_completion_in_geofence(self, geofence_entered, check_order_status=False):
        complete_on_entering = self.merchant.geofence_upon_entering and geofence_entered
        complete_on_exiting = not self.merchant.geofence_upon_entering and geofence_entered is False
        allow_order_completion = self.merchant.allow_geofence and (complete_on_entering or complete_on_exiting) \
                                 and self.driver_checklist_passed
        if check_order_status:
            allow_order_completion = allow_order_completion and \
                                     self.status not in self.get_current_available_statuses(OrderStatus.IN_PROGRESS)
        return allow_order_completion

    def set_duration_in_geofence_area(self, field_name, value):
        if value and hasattr(self, field_name):
            setattr(self, field_name, value)
            self.save(update_fields=(field_name,))

    def transform_description(self):
        RE = '(?P<url>%s)' % '|'.join([
            r'<(?:f|ht)tps?://[^>]*>',
            r'\b(?:f|ht)tps?://[^)<>\s]+[^.,)<>\s]',
            r'[^(<\s]+\.(?:[a-z]{2,6})\b',
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b'
        ])

        for url in re.findall(RE, self.description):
            if not url.split('://')[0] in ('http', 'https', 'ftp'):
                mdn_url = '[{0}](http://{0})'.format(url)
            else:
                mdn_url = '[{0}]({0})'.format(url)

            self.description = re.sub(r'(\\s+|^){0}(\\s+|$)'.format(re.escape(url)),
                                      r'\g<1>{0}\g<2>'.format(mdn_url), self.description)

    def get_track(self):
        items = []
        for serialized_item in self.serialized_track:
            track_item = DriverLocationSerializer(data=serialized_item)
            track_item.is_valid()
            items.append(DriverLocation(
                **dict(track_item.validated_data,
                       id=serialized_item['id'],
                       created_at=parser.parse(serialized_item['created_at']))
            ))
        return items

    def _get_path_info(self, start_status, end_statuses=None):
        from ..utils.order_path import Path

        end_statuses = end_statuses or [self.DELIVERED, self.FAILED]
        start = self.events.filter(new_value=start_status).values_list('happened_at', flat=True).last()
        finish = self.events.filter(new_value__in=end_statuses).values_list('happened_at', flat=True).last()
        if not (start and finish) or finish < start:
            path_info = Path()
        else:
            path_data = self.driver.serialize_track(start, finish)
            duration = finish - start
            path_info = Path(status=start_status, duration=duration, **path_data)
            if path_data['first_location']:
                path_info.starting_point = OrderLocation.from_location_object(path_data['first_location'])
        return path_info

    def finalize_order(self):
        from ..utils.order_path import Path

        status_chain = (self.PICK_UP, self.PICKED_UP, self.IN_PROGRESS, self.WAY_BACK, self.DELIVERED, self.FAILED)
        status_events = list(self.status_events.events.filter(new_value__in=status_chain).order_by('happened_at')
                             .values_list('new_value', flat=True))

        if len(status_events) == 1:
            statuses_path_map, full_path = {}, dict(Path().to_dict(), **{'started_at': timezone.now()})
        else:
            statuses_path_map = {status_events[i]: self._get_path_info(status_events[i], [status_events[i+1], ])
                                 for i in range(len(status_events)-1) if status_events[i] != self.PICKED_UP}
            full_path = reduce(operator.add, statuses_path_map.values())

        full_path_info = full_path if isinstance(full_path, dict) else full_path.to_dict()

        if self.PICK_UP in statuses_path_map:
            full_path_info.update({'pick_up_distance': statuses_path_map[self.PICK_UP].order_distance})
        if self.WAY_BACK in statuses_path_map:
            full_path_info.update({'wayback_distance': statuses_path_map[self.WAY_BACK].order_distance})

        for attr in ('changed_in_offline', 'starting_point'):
            if not full_path_info[attr]:
                del full_path_info[attr]

        Order.aggregated_objects.filter(id=self.id).update(**full_path_info)
        locations_cost = Order.aggregated_objects.get(id=self.id).locations_cost
        if locations_cost:
            self.merchant.change_balance(-locations_cost)

    @property
    def finalized(self):
        return self.path is not None

    @property
    def in_progress_point(self):
        return self.real_path.get(self.IN_PROGRESS, [])[0] if (self.real_path and self.real_path.get(self.IN_PROGRESS))\
            else None

    def merchant_daily_hash(self, merchant_id=None):
        _hash = hashlib.sha256()
        m_id = merchant_id or self.merchant_id
        _hash.update(settings.SECRET_KEY.encode() + bytes(m_id) + str(date.today()).encode())
        return binascii.hexlify(_hash.digest()).decode()

    def created_from_external_api(self):
        return True if self.external_job_id else False

    def show_customer_tracking_page(self):
        return self.status != self.FAILED and not self.deleted

    created_from_external_api.boolean = True
    created_from_external_api.short_description = 'External job'

    def __str__(self):
        return u'Order {title}'.format(
            title=self.title[0:30]
        )

    def get_order_status_map(self):
        status_map = OrderStatus._order_status_map
        if self.merchant.use_pick_up_status:
            status_map = dict(status_map, **OrderStatus._pick_up_modification)
        if self.merchant.use_way_back_status:
            status_map = dict(status_map, **OrderStatus._way_back_modification)
        return status_map

    def notify_pickup(self):
        if not self.pickup_id:
            return

        extra_context = {
            'merchant': self.sub_branding or self.merchant,
            'driver': self.driver,
            'tracking_url': self.get_order_url(delivery_route=False)
        }

        self.pickup.send_notification(
            template_type=MessageTemplateStatus.UPCOMING_PICK_UP,
            merchant_id=self.merchant_id,
            send_sms=self.merchant.sms_enable,
            sender=self.sub_branding.sms_sender if self.sub_branding_id else self.merchant.sms_sender,
            extra_context=extra_context
        )

    def notify_customer(self, template_type, send_sms=True, extra_context=None, **kwargs):
        extra_context = extra_context or {}
        extra_context.update(self.get_customizable_template_context(), **{'order': self})
        self.customer.send_notification(
            template_type=template_type,
            merchant_id=self.merchant_id,
            send_sms=send_sms and self.merchant.sms_enable,
            sender=self.sub_branding.sms_sender if self.sub_branding else self.merchant.sms_sender,
            extra_context=extra_context,
            **kwargs
        )

    def get_available_drivers(self):
        drivers = Member.drivers.all().filter(merchant_id=self.merchant_id)

        if self.merchant.enable_skill_sets:
            for skill_set in self.skill_sets.all():
                drivers = drivers.filter(skill_sets=skill_set)

        return drivers

    def handle_customer_rating(self):
        rating = self.rating
        if rating is None and self.customer_comment:
            rating = 0
        if rating is None or rating > self.merchant.low_feedback_value:
            return

        extra_context = {'order': self, 'customer': self.customer, 'report_url': self.full_report_link}
        extra_context.update(self.get_customizable_template_context())
        self.merchant.send_notification(
            MessageTemplateStatus.LOW_FEEDBACK,
            merchant_id=self.merchant_id,
            send_sms=False,
            extra_context=extra_context,
            email=self.merchant.call_center_email,
        )

    def handle_termination_code(self):
        extra_context = {
            'order': self,
            'customer': self.customer,
            'merchant': self.merchant,
            'report_url': self.full_report_link,
            'external_id': self.external_job.external_id if self.external_job_id else None
        }
        extra_context.update(self.get_customizable_template_context())

        for code in self.terminate_codes.all():
            code.send_notification(
                template_type=MessageTemplateStatus.ADVANCED_COMPLETION,
                merchant_id=self.merchant_id,
                send_sms=False,
                extra_context=extra_context
            )

    def handle_confirmation(self):
        if not self.status == OrderStatus.DELIVERED:
            return

        attachments = list(self._confirmation_attachments_generator())
        if not attachments:
            return

        extra_context = {
            'job': self,
            'external_id': self.external_job.external_id if self.external_job_id else None,
            'customer': self.customer
        }
        extra_context.update(self.get_customizable_template_context())

        self.merchant.send_pod_report_email(
            attachments=attachments, email=self.merchant.pod_email, extra_context=extra_context)

        if self.sub_branding:
            extra_context['merchant'] = self.sub_branding
            self.merchant.send_pod_report_email(
                email=self.sub_branding.pod_email,
                attachments=attachments,
                extra_context=extra_context
            )

    def _confirmation_attachments_generator(self):
        confirmations = list(self.order_confirmation_photos.values_list('image', flat=True))
        if self.confirmation_signature:
            confirmations.append(self.confirmation_signature.name)

        for confirmation in confirmations:
            with default_storage.open(confirmation, 'rb') as conf_file:
                attachment = ContentFile(conf_file.read())
                attachment.name = confirmation.split('/')[-1]
                yield attachment

    def get_customizable_template_context(self):
        date_format = date_template_format.US if settings.TIME_ZONE.startswith('US') else date_template_format.DEFAULT
        extra_context = {
            'job_deadline': DateFormat(self.deliver_before.astimezone(self.merchant.timezone)).format(date_format),
            'reference': self.title,
            'external_id': self.external_job.external_id if self.external_job_id else None
        }
        return extra_context

    @property
    def full_report_link(self):
        return settings.FRONTEND_URL + '/tracking/order/%s/full-report?merchant=%s&cluster_number=%s' % (
            self.id, self.merchant_id, settings.CLUSTER_NUMBER.lower(),
        )

    @property
    def public_report_link(self):
        if self.status not in OrderStatus.status_groups.FINISHED:
            return None
        uid = urlsafe_base64_encode(force_bytes(self.merchant.pk))
        link = u"{base_url}/public-report/{uid}/{token}?domain={domain}&cluster_number={cluster_number}".format(
            base_url=settings.FRONTEND_URL, uid=uid, token=self.order_token, domain=settings.CURRENT_HOST,
            cluster_number=settings.CLUSTER_NUMBER.lower(),
        )

        if self.merchant.shorten_report_url:
            return shortcut_link_safe(link)
        return link

    @property
    def customer_survey_enabled(self):
        if self.sub_branding:
            return self.sub_branding.customer_survey_enabled
        return self.merchant.customer_survey_enabled

    @property
    def customer_survey_template(self):
        if self.sub_branding:
            return self.sub_branding.customer_survey
        return self.merchant.customer_survey

    @property
    def finished_at(self):
        if self.status not in OrderStatus.status_groups.FINISHED:
            return None
        finish_event = self.status_events[OrderStatus.status_groups.FINISHED]
        return finish_event.happened_at if finish_event else None

    @property
    def route_optimisation_details(self):
        route_point_getter = self.order_route_point
        if not route_point_getter:
            if self.concatenated_order_id is not None:
                route_point_getter = self.concatenated_order.order_route_point
            if not route_point_getter:
                return

        result = {'pickup': None, 'delivery': None, 'queue': None}

        pickup_route_point = route_point_getter.get_by_kind(RoutePointKind.PICKUP)
        if pickup_route_point:
            after, before = pickup_route_point.planned_order_arrival_interval
            planned_arrival = pickup_route_point.start_time
            result['pickup'] = {
                'planned_arrival_after': after,
                'planned_arrival_before': before,
                'planned_arrival': planned_arrival,
            }

        delivery_route_point = route_point_getter.get_by_kind(RoutePointKind.DELIVERY)
        if not delivery_route_point and self.concatenated_order_id is not None:
            concatenated_order_route_point_getter = self.concatenated_order.order_route_point
            if concatenated_order_route_point_getter:
                delivery_route_point = concatenated_order_route_point_getter.get_by_kind(RoutePointKind.DELIVERY)
        if delivery_route_point:
            after, before = delivery_route_point.planned_order_arrival_interval
            planned_arrival = delivery_route_point.start_time
            result['delivery'] = {
                'planned_arrival_after': after,
                'planned_arrival_before': before,
                'planned_arrival': planned_arrival,
            }

        queue = self.in_driver_route_queue
        if queue['number'] is not None:
            result['queue'] = queue

        return result

    @property
    def aggregated_barcodes(self):
        if self.is_concatenated_order:
            barcodes = []
            for order in self.orders.all():
                for barcode in order.barcodes.all():
                    barcodes.append(barcode)
            return barcodes
        else:
            return list(self.barcodes.all())


class OrderPrice(Order):
    class Meta:
        proxy = True


class OrderConfirmationPhoto(TrackMixin, AttachedPhotoBase):
    thumbnailer = ThumbnailGenerator({'image': 'thumb_image_100x100_field'})
    tracker = FieldTracker()
    track_fields = {'image'}

    order = models.ForeignKey(Order, related_name='order_confirmation_photos', on_delete=models.CASCADE)
    _check_high_resolution = True

    @property
    def _merchant(self):
        return self.order.merchant


class OrderPreConfirmationPhoto(TrackMixin, AttachedPhotoBase):
    thumbnailer = ThumbnailGenerator({'image': 'thumb_image_100x100_field'})
    tracker = FieldTracker()
    track_fields = {'image'}

    order = models.ForeignKey(Order, related_name='pre_confirmation_photos', on_delete=models.CASCADE)
    _check_high_resolution = True

    @property
    def _merchant(self):
        return self.order.merchant


class OrderPickUpConfirmationPhoto(TrackMixin, AttachedPhotoBase):
    thumbnailer = ThumbnailGenerator({'image': 'thumb_image_100x100_field'})
    tracker = FieldTracker()
    track_fields = {'image'}

    order = models.ForeignKey(Order, related_name='pick_up_confirmation_photos', on_delete=models.CASCADE)
    _check_high_resolution = True

    @property
    def _merchant(self):
        return self.order.merchant
