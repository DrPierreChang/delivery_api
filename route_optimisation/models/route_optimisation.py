import logging
from datetime import datetime

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone

from model_utils import Choices

from reporting.context_managers import track_fields_on_change
from reporting.model_mapping import serializer_map
from reporting.models import Event
from reporting.signals import create_event, send_create_event_signal
from reporting.utils.delete import create_delete_event
from route_optimisation.const import OPTIMISATION_TYPES, GroupConst
from route_optimisation.logging import EventType, ROLogGetter

from .log import ROLog

logger = logging.getLogger('optimisation')


class RouteOptimisationQuerySet(models.QuerySet):
    def prefetch_related_data(self):
        from base.models import Member
        from route_optimisation.models import DriverRoute
        driver_routes_qs = DriverRoute.objects.all()\
            .prefetch_generic_relations()\
            .prefetch_related(
                models.Prefetch('driver', queryset=Member.drivers_with_statuses.all().select_related('car')),
            )
        return self\
            .select_related('merchant')\
            .prefetch_related(
                models.Prefetch('routes', queryset=driver_routes_qs),
                'delayed_task'
            )

    def prefetch_for_web_api(self):
        from route_optimisation.models import DriverRoute
        driver_routes_qs = DriverRoute.objects.all() \
            .prefetch_generic_relations_for_web_api()
        return self \
            .select_related('merchant') \
            .prefetch_related(
                models.Prefetch('routes', queryset=driver_routes_qs),
                'delayed_task'
            )


class RouteOptimisationManager(models.Manager):
    _queryset_class = RouteOptimisationQuerySet


class RouteOptimisation(ROLogGetter, models.Model):
    type = models.CharField(max_length=10, choices=OPTIMISATION_TYPES)

    merchant = models.ForeignKey('merchant.Merchant', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='optimisations')
    created_by = models.ForeignKey('base.Member', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_optimisations')

    day = models.DateField()
    options = JSONField(default=dict, blank=True)
    optimisation_options = JSONField(default=dict, blank=True)
    google_api_requests = JSONField(null=True, blank=True)

    optimisation_log = models.ForeignKey('route_optimisation.ROLog', on_delete=models.PROTECT, null=True, blank=True)

    STATE = Choices(
        ('CREATED', 'Created'),
        ('VALIDATION', 'Validation'),
        ('OPTIMISING', 'Optimising'),
        ('COMPLETED', 'Optimisation completed'),
        ('RUNNING', 'Running'),
        ('FINISHED', 'Finished'),
        ('FAILED', 'Failed'),
        ('REMOVED', 'Removed'),
    )
    state = models.CharField(max_length=12, choices=STATE, default=STATE.CREATED)

    customers_notified = models.BooleanField(default=False)
    is_removing_currently = models.BooleanField(default=False)

    external_source_id = models.PositiveIntegerField(null=True, blank=True)
    external_source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    external_source = GenericForeignKey('external_source_type', 'external_source_id')

    objects = RouteOptimisationManager()

    def save(self, *args, **kwargs):
        exists = bool(self.id)
        if not exists and not self.optimisation_log:
            self.optimisation_log = ROLog.objects.create()
        with track_fields_on_change(self, should_track=exists):
            super().save(*args, **kwargs)
        if not exists:
            serializer_class = serializer_map.get_for(self.__class__)
            dump = serializer_class(self).data
            dump.update({'str_repr': str(self), 'content_type': self.__class__.__name__.lower()})
            event = Event.generate_event(self, initiator=self.created_by,
                                         object=self,
                                         obj_dump=dump,
                                         event=Event.CREATED)
            send_create_event_signal(events=[event])

    def delete(self, using=None, unassign=False, initiator=None, cms_user=False, request=None, *args, **kwargs):
        self.refresh_from_db()
        if self.is_removing_currently or self.state == RouteOptimisation.STATE.REMOVED:
            return
        self.is_removing_currently = True
        self.save(update_fields=('is_removing_currently',))
        try:
            self.backend.on_delete(initiator, unassign, cms_user)
            self.state_to(RouteOptimisation.STATE.REMOVED)
            create_delete_event(self, self, initiator, request, merchant=self.merchant)
        except Exception as exc:
            logger.info(None, extra=dict(obj=self, event=EventType.EXCEPTION_ON_DELETION,
                                         event_kwargs={'exc': exc}))
            raise
        finally:
            self.is_removing_currently = False
            self.save(update_fields=('is_removing_currently',))
            if self.state != RouteOptimisation.STATE.REMOVED:
                create_event({}, {}, initiator=initiator, instance=self, sender=None, force_create=True)

    def terminate(self, initiator, request):
        self.backend.on_terminate(initiator)
        self.state_to(RouteOptimisation.STATE.REMOVED)
        create_delete_event(self, self, initiator, request, merchant=self.merchant)

    @property
    def is_terminated(self):
        self.optimisation_log.refresh_from_db()
        ro_events = set(map(lambda log_item: log_item['event'], self.optimisation_log.log['full']))
        return EventType.TERMINATE_RO in ro_events

    @property
    def backend(self):
        from route_optimisation.utils.backends.registry import backend_registry
        return backend_registry.get(self.type)(self)

    def state_to(self, state):
        logger.info(None, extra=dict(obj=self, event=EventType.RO_STATE_CHANGE, event_kwargs={'state': state}))
        self.state = state
        self.save(update_fields=('state',))

    @property
    def get_ro_log(self) -> ROLog:
        return self.optimisation_log

    @property
    def group(self):
        if self.state == RouteOptimisation.STATE.FAILED:
            return GroupConst.FAILED
        today = timezone.now().astimezone(self.merchant.timezone).date()
        if self.state in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING) and self.day > today:
            return GroupConst.SCHEDULED
        elif self.state in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING) and self.day == today:
            return GroupConst.CURRENT
        return None

    def notify_customers(self, initiator):
        logger.info(None, extra=dict(obj=self, event=EventType.NOTIFY_CUSTOMERS,
                                     event_kwargs={'initiator': initiator, 'code': 'request'}))
        from route_optimisation.celery_tasks.notification import notify_ro_customers
        notify_ro_customers.delay(self.id)
        self.customers_notified = True
        self.save(update_fields=('customers_notified',))

    @property
    def min_max_day_period(self):
        day_start = datetime.combine(self.day, datetime.min.time())
        day_start = self.merchant.timezone.localize(day_start)
        start_period = max(day_start, timezone.now().astimezone(self.merchant.timezone))
        end_period = datetime.combine(self.day, datetime.max.time())
        end_period = self.merchant.timezone.localize(end_period)
        return start_period, end_period

    @property
    def drivers(self):
        return [route.driver for route in self.routes.all()]

    def get_available_orders(self):
        from tasks.models import Order

        states = RouteOptimisation.STATE
        used_states = set(dict(states)) - {states.FAILED, states.REMOVED}
        orders_used_in_optimization_q = models.Q(
            models.Q(route_points__route__optimisation_id=self.id)
            | models.Q(route_points__route__optimisation__state__in=used_states)
        )
        start_period, end_period = self.min_max_day_period
        return Order.aggregated_objects.filter_by_merchant(self.merchant).filter(
            models.Q(deliver_after__isnull=True) | models.Q(deliver_after__lt=end_period),
            ~orders_used_in_optimization_q,
            deliver_before__gt=start_period,
            deliver_before__lt=end_period,
            status__in=[Order.NOT_ASSIGNED, Order.ASSIGNED],
        )

    @property
    def removing_currently(self):
        if self.state == RouteOptimisation.STATE.REMOVED:
            return False
        return self.is_removing_currently


class DummyOptimisation(ROLogGetter):
    def __init__(self, source_optimisation,  day, merchant, initiator, backend_name):
        self.source_optimisation = source_optimisation
        self.state = RouteOptimisation.STATE.CREATED
        self.day = day
        self.merchant = merchant
        self.optimisation_log = ROLog(log={})
        self.options = {}
        self.optimisation_options = {}
        self.created_by = initiator
        self.backend_name = backend_name
        self.google_api_requests = None

    min_max_day_period = RouteOptimisation.min_max_day_period
    get_available_orders = RouteOptimisation.get_available_orders

    @property
    def id(self):
        return self.source_optimisation.id

    @property
    def drivers(self):
        return self.source_optimisation.drivers

    @property
    def type(self):
        return self.source_optimisation.type

    @property
    def backend(self):
        from route_optimisation.utils.backends.registry import backend_registry
        return backend_registry.get(self.backend_name)(self)

    def state_to(self, state):
        self.state = state

    @property
    def get_ro_log(self) -> ROLog:
        return self.optimisation_log


class RefreshDummyOptimisation(DummyOptimisation):
    def state_to(self, state):
        logger.info(None, extra=dict(obj=self, event=EventType.REFRESH_STATE_CHANGE,
                                     event_kwargs={'initiator': self.created_by, 'state': state}))
        super().state_to(state)
