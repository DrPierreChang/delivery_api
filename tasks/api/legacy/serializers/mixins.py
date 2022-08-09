from __future__ import unicode_literals

import copy

from django.db.models.signals import post_save

from rest_framework.exceptions import ValidationError

from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.serializers.mixins import BaseUnpackMixin
from radaro_utils.serializers.validators import ValidateEarlierThanNowConfigurable
from routing.serializers import LocationUnpackMixin
from tasks.mixins.order_status import OrderStatus
from tasks.models import SKID, Barcode, Customer, Order, Pickup
from tasks.models.orders import order_deadline


class CustomerUnpackMixin(BaseUnpackMixin):
    customer_field_names = ('customer',)

    def unpack_fields(self, validated_data):
        super(CustomerUnpackMixin, self).unpack_fields(validated_data)
        context = getattr(self, 'context')
        if not context:
            raise ValidationError('CustomerUnpackMixin cannot access obligatory context.')
        try:
            user = context.get('user') or context.get('request').user
            if not user.current_merchant:
                raise ValidationError('Cannot pick up merchant from request.')
            for name in self.customer_field_names:
                from .customers import BaseCustomerSerializer
                customer_data = dict.fromkeys(BaseCustomerSerializer.unique_together_fields)
                try:
                    data = validated_data.pop(name)
                    # we pick merchant from validated data or context if jobs are being created using multi-key
                    merchant = validated_data.get('merchant') or context.get('merchant') or user.current_merchant
                    data['merchant_id'] = merchant.id
                    customer_data.update(data)
                    obj = Customer.objects.filter(**customer_data).last()
                    if not obj:
                        obj = Customer.objects.create(**data)
                    validated_data[name] = obj
                except KeyError:
                    pass
        except Exception:
            raise ValidationError('Cannot pick up user from request.')


class PickupUnpackMixin(BaseUnpackMixin):
    pickup_field_names = ('pickup',)

    def unpack_fields(self, validated_data):
        super().unpack_fields(validated_data)
        context = getattr(self, 'context')
        if not context:
            raise ValidationError('PickupUnpackMixin cannot access obligatory context.')
        try:
            user = context.get('user') or context.get('request').user
            if not user.current_merchant:
                raise ValidationError('Cannot pick up merchant from request.')
            for name in self.pickup_field_names:
                from .customers import PickupSerializer
                pickup_data = dict.fromkeys(PickupSerializer.unique_together_fields)
                try:
                    data = validated_data.pop(name)
                    if data is None:
                        validated_data[name] = data
                    else:
                        data['merchant_id'] = user.current_merchant_id
                        pickup_data.update(data)
                        obj = Pickup.objects.filter(**pickup_data).last()
                        if not obj:
                            obj = Pickup.objects.create(**data)
                        validated_data[name] = obj
                except KeyError:
                    pass
        except Exception:
            raise ValidationError('Cannot pick up user from request.')


class UnpackOrderPhotosMixin(BaseUnpackMixin):

    def unpack_fields(self, validated_data):
        super(UnpackOrderPhotosMixin, self).unpack_fields(validated_data)
        for item in self.confirmation_photos_list:
            field_name, model_class = item
            photos = validated_data.pop(field_name, [])
            if photos:
                photos = [model_class(order=self.instance, **item) for item in photos]
                photos = model_class.objects.bulk_create(photos)
                for photo in photos:
                    post_save.send(sender=model_class, instance=photo, created=True)


class ValidateJobIntervalsMixin:
    PICKUP_AFTER, PICKUP_BEFORE = 'pickup_after', 'pickup_before'
    DELIVER_AFTER, DELIVER_BEFORE = 'deliver_after', 'deliver_before'

    interval_bounds_map = {
        PICKUP_AFTER: 'Pick up after',
        PICKUP_BEFORE: 'Pick up deadline',
        DELIVER_AFTER: 'Deliver after',
        DELIVER_BEFORE: 'Delivery deadline'
    }

    def _validate_interval(self, attrs, merchant, bounds: tuple, default_upper_value=None):
        low, up = bounds
        lower_bound, upper_bound = attrs.get(low, getattr(self.instance, low) if self.instance else None), \
            attrs.get(up, getattr(self.instance, up) if self.instance else None)

        if not any([lower_bound, upper_bound]) and default_upper_value:
            attrs[up] = default_upper_value
        elif lower_bound and not upper_bound:
            raise ValidationError({up: "{} is required.".format(self.interval_bounds_map[up])})
        elif lower_bound and upper_bound:
            if lower_bound >= upper_bound:
                raise ValidationError("{} can't be earlier than {}."
                                      .format(self.interval_bounds_map[up], self.interval_bounds_map[low].lower()))
            lower, upper = lower_bound.astimezone(merchant.timezone), upper_bound.astimezone(merchant.timezone)
            if lower.date() != upper.date():
                raise ValidationError("{} and {} must be within one day."
                                      .format(self.interval_bounds_map[low], self.interval_bounds_map[up].lower()))

    def _validate_job_intervals(self, attrs, merchant):
        self._validate_interval(attrs, merchant, bounds=(self.DELIVER_AFTER, self.DELIVER_BEFORE))
        self._validate_interval(attrs, merchant, bounds=(self.PICKUP_AFTER, self.PICKUP_BEFORE))
        self._validate_interval(attrs, merchant, bounds=(self.PICKUP_BEFORE, self.DELIVER_BEFORE),
                                default_upper_value=order_deadline())


class ValidateConfirmationMixin(object):

    def _confirmation_validation(self, attrs, confirmation, can_confirm_with_status, is_confirmed,
                                 confirmation_enabled, confirmation_fields=[], pre=''):
        if not confirmation:
            return
        if not can_confirm_with_status:
            raise ValidationError("Invalid data.")
        elif is_confirmed:
            raise ValidationError("Order has been already {pre}confirmed.".format(pre=pre))
        elif not confirmation_enabled:
            for field in confirmation_fields:
                attrs.pop(field, None)

    def validate_pre_confirmation(self, attrs):
        status = attrs.get('status', self.instance.status)
        can_confirm_with_status = Order.can_pre_confirm_with_status(status)
        confirmation = attrs.get('pre_confirmation_signature') or attrs.get('pre_confirmation_photos')
        is_confirmed = self.instance.pre_confirmation_signature or self.instance.pre_confirmation_photos.exists()
        confirmation_enabled = self.instance.merchant.enable_delivery_pre_confirmation
        self._confirmation_validation(attrs, confirmation, can_confirm_with_status, is_confirmed, confirmation_enabled,
                                      confirmation_fields=['pre_confirmation_signature', 'pre_confirmation_photos'],
                                      pre='pre')

    def validate_confirmation(self, attrs):
        status = attrs.get('status', self.instance.status)
        can_confirm_with_status = Order.can_confirm_with_status(status)
        confirmation = attrs.get('confirmation_signature') or attrs.get('order_confirmation_photos')
        is_confirmed = self.instance.confirmation_signature or self.instance.order_confirmation_photos.exists()
        confirmation_enabled = self.instance.merchant.enable_delivery_confirmation

        self._confirmation_validation(attrs, confirmation, can_confirm_with_status, is_confirmed, confirmation_enabled,
                                      confirmation_fields=['confirmation_signature', 'order_confirmation_photos'])

    def validate_pick_up_confirmation(self, attrs):
        status = attrs.get('status', self.instance.status)
        can_confirm_with_status = Order.can_confirm_pick_up_with_status(status)
        confirmation = attrs.get('pick_up_confirmation_signature') or attrs.get('pick_up_confirmation_photos') \
            or attrs.get('pick_up_confirmation_comment')
        is_confirmed = self.instance.pick_up_confirmation_signature \
            or self.instance.pick_up_confirmation_photos.exists() \
            or self.instance.pick_up_confirmation_comment
        confirmation_enabled = self.instance.merchant.enable_pick_up_confirmation
        self._confirmation_validation(attrs, confirmation, can_confirm_with_status, is_confirmed, confirmation_enabled,
                                      confirmation_fields=[
                                          'pick_up_confirmation_signature', 'pick_up_confirmation_photos',
                                          'pick_up_confirmation_comment'
                                      ])

    def validate(self, attrs):
        super(ValidateConfirmationMixin, self).validate(attrs)
        self.validate_pre_confirmation(attrs)
        self.validate_confirmation(attrs)
        self.validate_pick_up_confirmation(attrs)


class OrderLocationUnpackMixin(LocationUnpackMixin):
    def to_internal_value(self, data):
        # legacy 'address_2' fields compatibility
        for address, address_2 in (('deliver_address', 'deliver_address_2'), ('pickup_address', 'pickup_address_2')):
            if address_2 not in data:
                continue
            if address not in data:
                data[address] = self._copy_address_data(address)
            data.get(address).update({'secondary_address': data.pop(address_2)}) if data.get(address) is not None \
                else data.pop(address_2)
        return super().to_internal_value(data)

    def _copy_address_data(self, address_field):
        location_serializer = type(self.fields[address_field])
        return copy.deepcopy(location_serializer(getattr(self.instance, address_field) if self.instance else None).data)

    def _get_location_object(self, location, data):
        return self.location_class.objects.get_or_create(
            location=location,
            address=data.get('address', ''),
            raw_address=data.get('raw_address', ''),
            secondary_address=data.get('secondary_address', ''),
            defaults=data
        )


class ActiveOrdersChangesValidationMixin(object):
    ACTIVE_ERROR = 'active_error'
    ASSIGNED_ERROR = 'assigned_error'

    def _get_active_error_msg(self, jobs_ids, relations):
        return

    def _get_assigned_error_msg(self, jobs_ids, relations):
        return

    def _validate_active_jobs(self, jobs_ids, relations):
        if not jobs_ids:
            return
        error_msg = self._get_active_error_msg(jobs_ids, relations)
        raise ValidationError({self.ACTIVE_ERROR: error_msg})

    def _validate_assigned_jobs(self, jobs_ids, relations, background_notification):
        request = self.context.get('request')

        if jobs_ids and 'force' not in request.query_params:
            error_msg = self._get_assigned_error_msg(jobs_ids, relations)
            raise ValidationError({self.ASSIGNED_ERROR: error_msg})

        Order.aggregated_objects.bulk_status_change(
            order_ids=jobs_ids,
            to_status=OrderStatus.NOT_ASSIGNED,
            initiator=request.user,
            background_notification=background_notification
        )

    def _validate_on_destroy(self, relations, jobs_qs, background_notification=False):
        jobs = jobs_qs.values('active', 'assigned', 'id')

        active_jobs_ids = [item['id'] for item in jobs if item['active']]
        self._validate_active_jobs(active_jobs_ids, relations)

        assigned_jobs_ids = [item['id'] for item in jobs if item['assigned']]
        self._validate_assigned_jobs(assigned_jobs_ids, relations, background_notification)


class BarcodesUnpackMixin(BaseUnpackMixin):

    def update(self, instance, validated_data):
        barcodes = validated_data.pop('barcodes', [])
        if not barcodes:
            return super(BarcodesUnpackMixin, self).update(instance, validated_data)

        barcodes_to_remove = []
        barcodes_to_create = []

        for data in barcodes:
            code_id = data.pop('id', None)
            if code_id:
                if not data:
                    # Remove barcode if only `id` was provided
                    barcodes_to_remove.append(code_id)
                    continue
                # Update barcode with the new data by id
                Barcode.objects.filter(id=code_id).update(**data)
            else:
                # Create new barcode with the data if `id` was not provided
                barcodes_to_create.append(Barcode(order=instance, **data))
        Barcode.objects.filter(id__in=barcodes_to_remove).delete()
        Barcode.objects.bulk_create(barcodes_to_create)

        return super(BarcodesUnpackMixin, self).update(instance, validated_data)

    def create(self, validated_data):
        barcodes = validated_data.pop('barcodes', [])
        instance = super(BarcodesUnpackMixin, self).create(validated_data)
        Barcode.objects.bulk_create(Barcode(order=instance, **code_info) for code_info in barcodes)
        return instance


class ExternalBarcodesUnpackMixin(BaseUnpackMixin):

    def unpack_fields(self, validated_data):
        super(ExternalBarcodesUnpackMixin, self).unpack_fields(validated_data)
        barcodes = validated_data.pop('barcodes', [])
        validated_data['barcodes'] = (Barcode(**code_info) for code_info in barcodes)


class ExternalSkidsUnpackMixin(BaseUnpackMixin):

    def unpack_fields(self, validated_data):
        super().unpack_fields(validated_data)
        skids = validated_data.pop('skids', [])
        validated_data['skids'] = (SKID(**skid) for skid in skids)


class OfflineHappenedAtMixin(object):
    offline_happened_at = UTCTimestampField(required=False)

    def validate(self, attrs):
        if 'offline_happened_at' in attrs:
            try:
                ValidateEarlierThanNowConfigurable()(attrs['offline_happened_at'])
            except ValidationError as ex:
                if self.context['request'].version >= 2:
                    raise ValidationError({'offline_happened_at': ex.detail})
                else:
                    raise
        return super(OfflineHappenedAtMixin, self).validate(attrs)
