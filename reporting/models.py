# coding=utf-8
from __future__ import unicode_literals

import itertools as it_
import math
import uuid
from operator import itemgetter

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Count, Max, Q, prefetch_related_objects
from django.utils import timezone
from django.utils.text import slugify

from crequest.middleware import CrequestMiddleware
from jsonfield import JSONField

from merchant.models import Merchant
from radaro_utils.fields import CustomDateTimeField, CustomFileField
from radaro_utils.files.utils import delayed_task_upload
from radaro_utils.helpers import spaces_to_underscores
from radaro_utils.radaro_delayed_tasks.models import DelayedTaskBase
from reporting.model_mapping import serializer_map


class EventManager(models.Manager):
    @property
    def EVENTS_ENABLED_FOR(self):
        return [
            ContentType.objects.get_for_model(it, for_concrete_model=False) for it in serializer_map._mapping.keys()
        ]

    duration_query = """SELECT r1.id, f - s + INTERVAL '1 minutes' AS duration
                        FROM
                            (SELECT DISTINCT ON (re1.object_id) re1.id, re1.object_id, re1.happened_at AS s
                            FROM reporting_event re1
                            WHERE field = %(first_field)s AND new_value = %(first_value)s
                            AND object_id=%(object_id)s AND content_type_id=%(content_type_id)s 
                            ORDER BY re1.object_id, re1.happened_at DESC ) AS r1
                        INNER JOIN
                            (SELECT DISTINCT ON (re2.object_id) re2.id, re2.object_id, re2.happened_at AS f
                            FROM reporting_event re2
                            WHERE field = %(second_field)s AND new_value = %(second_value)s
                            AND object_id=%(object_id)s AND content_type_id=%(content_type_id)s 
                            ORDER BY re2.object_id, re2.happened_at DESC ) AS r2
                        ON r1.object_id = r2.object_id WHERE f > s"""

    def last_events(self, merchant, date_since):
        return self.filter(
            merchant=merchant,
            created_at__gt=date_since,
            content_type__in=self.EVENTS_ENABLED_FOR,
            event__in=[Event.CREATED, Event.DELETED, Event.MODEL_CHANGED],
        ).select_related('initiator__car').prefetch_related('object').order_by('created_at')

    def _get_duration(self, order, first_field, first_value, second_field, second_value):
        if order:
            from tasks.models import ConcatenatedOrder, Order
            model = ConcatenatedOrder if order.is_concatenated_order else Order
            params = {
                'object_id': order.id,
                'content_type_id': ContentType.objects.get_for_model(model, for_concrete_model=False).id,
                'first_field': first_field,
                'first_value': first_value,
                'second_field': second_field,
                'second_value': second_value,
            }
            result = self.raw(self.duration_query, params)[:]
            result = result[-1].duration if result else None
            return result

    def time_inside_pickup_geofence(self, order=None):
        return self._get_duration(order, first_field='pickup_geofence_entered', first_value='True',
                                  second_field='pickup_geofence_entered', second_value='False')

    def time_at_pickup(self, order=None, to_status=None):
        return self._get_duration(order, first_field='pickup_geofence_entered', first_value='True',
                                  second_field='status', second_value=to_status)

    def time_inside_geofence(self, order=None, flat=False):
        return self._get_duration(order, first_field='geofence_entered', first_value='True',
                                  second_field='geofence_entered', second_value='False')

    def time_at_job(self, order=None, flat=False):
        return self._get_duration(order, first_field='geofence_entered', first_value='True',
                                  second_field='status', second_value='delivered')

    def customer_tracking(self, order, trackable_statuses):
        return self.get_queryset().filter(object_id=order.id, content_type__model='order')\
            .filter(Q(field='status') & Q(new_value__in=trackable_statuses) |
                    Q(field='customer') & Q(event=Event.CREATED))\
            .order_by('-happened_at')

    def pickup_tracking(self, order, trackable_statuses):
        qs = self.get_queryset().filter(object_id=order.id, content_type__model='order',
                                        field='status', new_value__in=trackable_statuses) \
                                .order_by('-happened_at')
        return qs

    def get_related_dates(self, related_fields, related_values, objects=None):
        if objects is None:
            return {}

        if isinstance(objects, models.query.QuerySet):
            ids = objects
            Model = objects.model
        else:
            ids = [obj.id for obj in objects]
            Model = type(objects[-1])

        return self.get_queryset() \
            .filter(content_type_id=ContentType.objects.get_for_model(Model, for_concrete_model=False).id,
                    object_id__in=ids,
                    field__in=related_fields,
                    new_value__in=related_values) \
            .values('object_id', 'new_value', 'field') \
            .annotate(Max('happened_at'))

    @staticmethod
    def filter_out_without_object(events):
        """ Filter out events that link to empty objects, because these events are useless. """
        return filter(lambda ev: not (ev.event != Event.DELETED and ev.object is None), events)

    def pick_related_dates(self, related_fields, related_values, objects=None):
        change_stats = {}

        events = self.get_related_dates(related_fields, related_values, objects).order_by('object_id')

        for obj_id, _events in it_.groupby(events, itemgetter('object_id')):
            change_stats[obj_id] = {field: {event['new_value']: event['happened_at__max'] for event in _group}
                                    for field, _group in it_.groupby(_events, itemgetter('field'))}

        return change_stats

    def pick_report_related_dates(self, related_fields, related_values, map_fields, objects=None):
        events_stats = {}

        events = self.get_related_dates(related_fields, related_values, objects)\
            .order_by('object_id', 'field', '-happened_at__max')

        for ord_id, _events in it_.groupby(events, itemgetter('object_id')):
            events_stats[ord_id] = {map_fields[f]: next(_gr_ev)['happened_at__max']
                                    for f, _gr_ev in it_.groupby(_events, itemgetter('field'))}

        return events_stats

    @classmethod
    def prefetch_related_for_orders(cls, events):
        from tasks.models import Order
        prefetch_list = (
            'object__merchant', 'object__customer', 'object__manager',
            'object__pre_confirmation_photos', 'object__pick_up_confirmation_photos',
            'object__order_confirmation_photos', 'object__order_confirmation_documents',
            'object__labels', 'object__terminate_codes', 'object__barcodes', 'object__driver_checklist',
            'object__skill_sets', 'object__starting_point', 'object__ending_point', 'object__deliver_address',
            'object__pickup_address', 'object__wayback_point', 'object__pickup', 'object__skids',
            models.Prefetch('object__status_events', to_attr=Order.status_events.cache_name)
        )
        order_ct = ContentType.objects.get_for_model(Order)
        order_events = [event for event in events if event.content_type == order_ct]
        prefetch_related_objects(order_events, *prefetch_list)
        return events

    @classmethod
    def prefetch_related_for_drivers(cls, events):
        from base.models import Member
        from tasks.mixins.order_status import OrderStatus
        from tasks.models import BulkDelayedUpload
        prefetch_list = (
            'object__merchant__checklist', 'object__car', 'object__skill_sets', 'object__last_location',
        )
        driver_ct = ContentType.objects.get_for_model(Member)
        driver_events = [event for event in events if event.content_type == driver_ct]
        prefetch_related_objects(driver_events, *prefetch_list)

        # It uses the existing functionality that allows you to get the status of all drivers in one request
        drivers = {event.object_id: event.object for event in driver_events if event.object is not None}
        from driver.queries import QUERY_ANNOTATION
        driver_statuses = Member.all_objects.filter(id__in=drivers.keys()).annotate(
            _status=QUERY_ANNOTATION,
            active_orders_count=Count(
                'order',
                filter=Q(
                    Q(order__bulk__isnull=True) | Q(order__bulk__status=BulkDelayedUpload.CONFIRMED),
                    order__deleted=False, order__status__in=OrderStatus.status_groups.ACTIVE_DRIVER
                )
            ),
        ).values('id', '_status', 'active_orders_count')
        for status in driver_statuses:
            drivers[status['id']]._status = status['_status']
            drivers[status['id']].active_orders_count = status['active_orders_count']

        return events

    @classmethod
    def prefetch_related_for_optimisation(cls, events):
        from route_optimisation.models import DriverRoute, RouteOptimisation
        ro_ct = ContentType.objects.get_for_model(RouteOptimisation)
        ro_events = [event for event in events if event.content_type == ro_ct]
        driver_routes_qs = DriverRoute.objects.all() \
            .prefetch_generic_relations_for_web_api()
        prefetch_list = ('object__merchant', models.Prefetch('object__routes', queryset=driver_routes_qs),
                         'object__delayed_task', 'object__optimisation_log',)
        prefetch_related_objects(ro_events, *prefetch_list)
        return events

    @classmethod
    def prepare_for_list(cls, events):
        events = list(events)
        events = cls.prefetch_related_for_orders(events)
        events = cls.prefetch_related_for_drivers(events)
        events = cls.prefetch_related_for_optimisation(events)
        return events


class Event(models.Model):
    DELETED = -1
    CREATED = 0
    CHANGED = 1
    MODEL_CHANGED = 2

    _action = (
        (DELETED, 'deleted'),
        (CREATED, 'created'),
        (CHANGED, 'changed'),
        (MODEL_CHANGED, 'model_changed'),
    )

    created_at = CustomDateTimeField(auto_now_add=True)
    happened_at = CustomDateTimeField(auto_now_add=True)
    initiator = models.ForeignKey('base.Member', null=True, blank=True, on_delete=models.SET_NULL)
    merchant = models.ForeignKey('merchant.Merchant', null=True, blank=True, on_delete=models.SET_NULL)
    event = models.IntegerField(choices=_action, default=CREATED)

    field = models.CharField(max_length=45, null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    comment = models.TextField(blank=True)
    obj_dump = JSONField(blank=True, null=True)
    detailed_dump = JSONField(blank=True, null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object = GenericForeignKey('content_type', 'object_id', for_concrete_model=False)

    objects = EventManager()

    class Meta:
        ordering = ('-happened_at', )
        indexes = [
            models.Index(fields=['merchant', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    @property
    def object_name(self):
        try:
            return self.object or self.obj_dump['str_repr']
        except (AttributeError, KeyError, TypeError):
            return None

    def __str__(self):
        return u'Event "{did}" on {field} {on_what} at {time}'.format(
            did=self.get_event_display(),
            field='' if self.event in [self.DELETED, self.CREATED] or not self.field else u'{} on'.format(self.field),
            on_what=self.object_id,
            time=self.happened_at
        )

    def save(self, *args, **kwargs):
        if not self.id:
            self.created_at = timezone.now()
            self.happened_at = self.happened_at or self.created_at
        super(Event, self).save(*args, **kwargs)

    @property
    def is_online(self):
        return self.created_at == self.happened_at

    def get_content_type_model(self):
        """
        When making queryset like Event.objects.prefetch_related('object'), then objects from this queryset can contain
        the content_type field equals None, although physically each event has content_type in database. This is the
        problem of GenericFK and prefetch_related, in case when an object that the event referenced isn't in the
        database (object was deleted earlier). So we just update the content_type field for this object from database.
        """
        if not self.content_type:
            # Refresh event's content_type
            self.content_type = Event.objects.get(id=self.id).content_type
        if self.content_type:
            return self.content_type.model
        from reporting.celery_tasks import notify_about_event_without_content_type
        notify_about_event_without_content_type.delay(self.id)

    # Set initiator as None if use in Celery task and initiator is unknown
    @staticmethod
    def generate_event(sender, initiator=False, **kwargs):
        obj = kwargs.pop('object')
        if not initiator and initiator is not None:
            initiator = CrequestMiddleware.get_request().user

        if kwargs['event'] == Event.DELETED:
            kwargs['obj_dump'] = obj
            kwargs['content_type'] = obj.pop('content_type')
            merchant_id = obj.get('merchant_id', obj.get('merchant', None)) or getattr(initiator, 'merchant_id', None)
        else:
            kwargs['object'] = obj
            merchant_id = (
                    getattr(obj, 'current_merchant_id', None)
                    or getattr(obj, 'merchant_id', None)
                    or getattr(initiator, 'current_merchant_id', None)
            )

        if merchant_id is None:
            return None

        event = Event.objects.create(initiator=initiator, merchant_id=merchant_id, **kwargs)
        from reporting.signals import event_created
        event_created.send(sender=sender, event=event)
        return event


class ExportDataMixin(object):
    @staticmethod
    def _csv_format_name(driver_id=None, **kwargs):
        return spaces_to_underscores(driver_id.full_name if driver_id else 'all_drivers')


class ExportReportInstance(ExportDataMixin, DelayedTaskBase):
    file = CustomFileField(upload_to=delayed_task_upload, null=True)
    initiator = models.ForeignKey('base.Member', null=True, blank=True, on_delete=models.SET_NULL)
    merchant = models.ForeignKey('merchant.Merchant', null=True, on_delete=models.PROTECT)

    @property
    def encoding(self):
        return 'utf-8'

    @property
    def date_format(self):
        _date_format = self.merchant.date_format if self.merchant \
            else settings.DEFAULT_DATE_FORMAT

        return '%m-%d' if _date_format == Merchant.MIDDLE_ENDIAN else '%d-%m'

    def _prepare_file_name(self, file_name, unique_name, date_from=None, date_to=None, period=None, **report_params):
        if not file_name:
            file_name = self._csv_format_name(**report_params)
        report_period = ''
        try:
            low, up = (date_from, date_to) if not period else (period['from'], period['to'])
            if low and up:
                report_period = '_{}-{}'.format(
                    low.strftime(self.date_format),
                    up.strftime(self.date_format)
                )
        except ValueError:
            report_period = '_unknown_date'

        unique_str = '' if not unique_name else '_' + str(uuid.uuid4())
        return slugify(f'{file_name}{report_period}{unique_str}') + '.csv'

    def prepare_file(self, report_params, file_name, unique_name=False, period=None):
        file_name = self._prepare_file_name(file_name, unique_name, period=period, **report_params)
        file_ = ContentFile(b'')
        self.file.save(file_name, file_)

    def open_file(self):
        _file = self.file
        _file.open('wt')
        return _file

    def close_file(self, _file):
        _file.close()

    def _when_begin(self, report_writer, format_='csv', *args, **kwargs):
        prg_step = 1.
        for _ in report_writer:
            prg = math.floor(prg_step / report_writer.chunks * 100)
            self.event('{}%'.format(prg), ExportReportInstance.PROGRESS)
            prg_step += 1.

    def _when_fail(self, message, *args, **kwargs):
        self.event(message, ExportReportInstance.ERROR)

    def _when_complete(self, *args, **kwargs):
        self.event('Ready.', ExportReportInstance.INFO)

    def upload_path(self, instance, filename):
        return '{0}/{1}'.format(type(instance).__name__, filename)

    def build_csv_report(self, writer_class, params, file_name=None, unique_name=True):
        try:
            period = params.pop('period', None)
            self.prepare_file(params, unique_name=unique_name, file_name=file_name, period=period)
            writer = writer_class(self, params)
            self.begin(writer, 'csv')
            self.complete()
        except Exception as ex:
            if self.pk:
                self.fail(message=str(ex) or 'Error while composing report.')
                raise
        finally:
            self.save()
