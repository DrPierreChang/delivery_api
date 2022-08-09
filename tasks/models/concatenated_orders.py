import datetime
import itertools
import uuid

from django.db import models, transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.functional import cached_property

from rest_framework.fields import empty

from merchant.models import SkillSet

from ..mixins.order_status import OrderStatus
from .orders import BaseOrderQuerySet, Order


class ConcatenatedOrderQuerySet(BaseOrderQuerySet):
    def prefetch_for_mobile_api(self):
        return self.select_related(
            'customer', 'deliver_address'
        ).prefetch_related(
            'skill_sets', 'labels',
            Prefetch('orders', queryset=Order.objects.all().prefetch_for_mobile_api().order_inside_concatenated()),
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
        )

    def prefetch_for_web_api(self):
        return self.select_related(
            'customer', 'deliver_address',
        ).prefetch_related(
            'skill_sets', 'labels',
            Prefetch('orders', queryset=Order.objects.all().prefetch_for_web_api().order_inside_concatenated()),
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
        )


class ConcatenatedOrderManager(models.Manager):
    def get_queryset(self):
        return ConcatenatedOrderQuerySet(self.model, using=self._db).filter(deleted=False, is_concatenated_order=True)

    def filter_by_order(self, order):
        return self.filter(
            merchant_id=order.merchant_id,
            driver_id=order.driver_id,
            status=order.status,
            deliver_day=order.deliver_before.astimezone(order.merchant.timezone).date(),
            customer_id=order.customer_id,
            deliver_address_id=order.deliver_address_id,
        )

    def create_from_order(self, order):
        with transaction.atomic():
            instance = self.create(
                merchant_id=order.merchant_id,
                driver_id=order.driver_id,
                manager_id=order.manager_id,
                status=order.status,
                deliver_day=order.deliver_before.astimezone(order.merchant.timezone).date(),
                deliver_before=order.deliver_before,
                customer_id=order.customer_id,
                deliver_address_id=order.deliver_address_id,
                is_concatenated_order=True,
            )
            order.concatenated_order = instance
            Order.all_objects.filter(id=order.id).update(concatenated_order=instance)
        return instance


class DeletedConcatenatedOrderManager(models.Manager):
    def get_queryset(self):
        return ConcatenatedOrderQuerySet(self.model, using=self._db).filter(is_concatenated_order=True)


class ConcatenatedOrder(Order):
    objects = ConcatenatedOrderManager()
    all_objects = DeletedConcatenatedOrderManager()

    class Meta:
        proxy = True
        ordering = ('id',)
        verbose_name = 'Concatenated order'
        verbose_name_plural = 'Concatenated orders'
        default_related_name = 'concatenated_orders'

    def __str__(self):
        return f'Concatenated order {self.id}'

    def nested_orders_save(self, existed_concatenated_order):
        shared_fields = {
            'is_confirmed_by_customer', 'customer_review_opt_in', 'rating', 'customer_comment', 'driver_id',
            'starting_point', 'ending_point', 'wayback_point', 'terminate_comment', 'changed_in_offline',

            'pre_confirmation_signature', 'thumb_pre_confirmation_signature_100x100_field',
            'confirmation_signature', 'thumb_confirmation_signature_100x100_field',
            'confirmation_comment', 'pre_confirmation_comment',

            'geofence_entered', 'is_completed_by_geofence', 'time_inside_geofence', 'time_at_job',
        }
        pickup_shared_fields = {
            'pick_up_confirmation_signature', 'thumb_pick_up_confirmation_signature_100x100_field',
            'pick_up_confirmation_comment',
        }
        exclude_should_notify = {
            'confirmation_signature', 'pre_confirmation_signature', 'pick_up_confirmation_signature',
        }

        changed_fields = {}
        for field in shared_fields | pickup_shared_fields | {'status'}:
            if getattr(self, field) != getattr(existed_concatenated_order, field):
                changed_fields[field] = getattr(self, field)

        changed_orders = []
        if changed_fields:
            for order in self.active_nested_orders:
                for field, value in changed_fields.items():
                    if field in shared_fields:
                        setattr(order, field, changed_fields[field])

                if order.pickup_address_id:
                    for field, value in changed_fields.items():
                        if field in pickup_shared_fields:
                            setattr(order, field, changed_fields[field])

                if order.status != OrderStatus.FAILED:
                    if not (self.status in [order.PICK_UP, order.PICKED_UP] and not order.pickup_address_id):
                        order.status = self.status

                order.save(exclude_should_notify=exclude_should_notify)
                changed_orders.append(order)

        return changed_orders

    def save(self, existed_concatenated_order=empty, *args, **kwargs):
        if existed_concatenated_order is empty:
            existed_concatenated_order = ConcatenatedOrder.objects.filter(pk=self.pk).first() if self.pk else None

        if not self.order_id:
            self.order_id = self.generate_id()
        if not self.order_token:
            self.order_token = uuid.uuid4()
        if not self.title:
            self.title = 'Job: ID ' + str(self.order_id)

        super(Order, self).save(*args, **kwargs)
        if existed_concatenated_order:
            self.nested_orders_save(existed_concatenated_order)

    def update_data(self):
        orders = Order.all_objects.filter(concatenated_order=self, deleted=False).order_inside_concatenated()
        orders = list(orders)

        if orders:
            self.title = ', '.join(order.title for order in orders)[:255]

            nested_capacity_list = [order.capacity for order in orders if order.capacity is not None]
            if len(nested_capacity_list) > 0:
                self.capacity = sum(nested_capacity_list)
            else:
                self.capacity = None

            # The interval is taken from the undelivered order with the smallest deliver_before
            # If there are several smallest deliver_before, the interval is taken with the smallest deliver_after
            # deliver_after = None if all of the orders have deliver_after set to None
            unfinished_orders = [
                order for order in orders
                if order.status not in [OrderStatus.WAY_BACK, OrderStatus.DELIVERED, OrderStatus.FAILED]
            ]
            if unfinished_orders:
                earlier_order = min(
                    unfinished_orders,
                    key=lambda order: (order.deliver_before, order.deliver_after or order.deliver_before)
                )
                self.deliver_before, self.deliver_after = earlier_order.deliver_before, earlier_order.deliver_after

                skill_sets = set(itertools.chain.from_iterable(
                    order.skill_sets.all().values_list('id', flat=True) for order in orders
                ))
                self.skill_sets.set(skill_sets)

                labels = set(itertools.chain.from_iterable(
                    order.labels.all().values_list('id', flat=True) for order in orders
                ))
                self.labels.set(labels)

        self.updated_at = timezone.now()
        self.save(update_fields=('updated_at', 'title', 'capacity', 'deliver_before', 'deliver_after'))

    @property
    def active_nested_orders(self):
        nested_orders = self.orders.all()
        if self.status != OrderStatus.FAILED:
            nested_orders = nested_orders.exclude(status=Order.FAILED)
        return nested_orders

    @property
    def available_orders(self):
        deliver_day = datetime.datetime.combine(self.deliver_day, datetime.datetime.min.time())
        deliver_day = self.merchant.timezone.localize(deliver_day)
        orders = Order.objects.filter(
            merchant_id=self.merchant_id,
            customer_id=self.customer_id,
            deliver_address_id=self.deliver_address_id,
            concatenated_order__isnull=True,
            deliver_before__range=(deliver_day, deliver_day + datetime.timedelta(days=1))
        )

        jobs_filter = Q(driver_id=self.driver_id, status=self.status)
        if self.status == self.ASSIGNED:
            free_jobs_filter = Q(
                driver__isnull=True,
                status=Order.NOT_ASSIGNED,
            )
            if self.merchant.enable_skill_sets:
                exclude_skills = SkillSet.objects.exclude(drivers=self.driver).filter(merchant_id=self.merchant_id)
                free_jobs_filter &= ~Q(skill_sets__in=exclude_skills)

            jobs_filter |= free_jobs_filter

        return orders.filter(jobs_filter)

    @property
    def all_available_orders(self):
        return self.available_orders | Order.objects.filter(concatenated_order=self)

    @property
    def pickups(self):
        pickups = {}
        for order in self.orders.all():
            if order.pickup_address_id and (order.status != OrderStatus.FAILED or self.status == OrderStatus.FAILED):
                if order.pickup_address_id not in pickups.keys():
                    pickups[order.pickup_address_id] = {
                        'pickup_address': order.pickup_address,
                        'pickup': order.pickup,
                        'interval': [(order.pickup_before, order.pickup_after)],
                    }
                else:
                    pickups[order.pickup_address_id]['interval'].append((order.pickup_before, order.pickup_after))

        result = []
        for pickup in pickups.values():
            pickup_before, pickup_after = min(
                    pickup['interval'],
                    key=lambda interval: (interval[0] or self.deliver_before, interval[1] or self.deliver_before)
                )
            result.append({
                'pickup_address': pickup['pickup_address'],
                'pickup': pickup['pickup'],
                'pickup_before': pickup_before,
                'pickup_after': pickup_after,
            })

        return result

    @cached_property
    def pickup_interval(self):
        intervals = [(None, None)]
        for order in self.orders.all():
            if order.pickup_address_id and (order.status != OrderStatus.FAILED or self.status == OrderStatus.FAILED):
                intervals.append((order.pickup_before, order.pickup_after))

        pickup_before, pickup_after = min(
            intervals,
            key=lambda interval: (interval[0] or self.deliver_before, interval[1] or self.deliver_before)
        )
        return {'before': pickup_before, 'after': pickup_after}

    def safe_delete(self, *args, **kwargs):
        Order.objects.filter(concatenated_order=self).update(concatenated_order=None)
        self.deleted = True
        self.save(update_fields=('deleted',))

    def _calculate_order_distance(self, to_status):
        if self.starting_point is None:
            return
        points = [self.starting_point.location, ]
        points.append(self.deliver_address.location)
        self._pre_calculate_order_distance(points, to_status)

    def _pre_calculate_order_distance(self, points, to_status):
        distances = self._calculate_distances(points)
        if distances is not None:
            self.order_distance = sum(distances)
