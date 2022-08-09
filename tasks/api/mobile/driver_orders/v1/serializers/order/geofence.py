from rest_framework import serializers

from radaro_utils.serializers.validators import ValidateLaterDoesNotExist
from reporting.models import Event
from tasks.api.mobile.driver_orders.v1.serializers import OfflineOrderMixinSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.push_notification.push_messages.event_composers import ChecklistMessage


class OrderGeofenceStatusValidator:
    message = 'You cannot send geofence data in current order status.'
    allowed_statuses = (OrderStatus.PICK_UP, OrderStatus.IN_PROGRESS)

    instance = None

    def set_context(self, serializer_field):
        self.instance = getattr(serializer_field.root, 'instance', None)

    def __call__(self, *args, **kwargs):
        if self.instance and self.instance.status not in self.allowed_statuses:
            raise serializers.ValidationError(self.message, code='invalid_status')


class OrderGeofenceSerializer(OfflineOrderMixinSerializer, serializers.ModelSerializer):
    geofence_entered = serializers.BooleanField(required=True, allow_null=False,
                                                validators=[OrderGeofenceStatusValidator()])

    class Meta:
        model = Order
        fields = ('geofence_entered', 'offline_happened_at')

    def validate_geofence_entered(self, geofence_entered):
        order = self.instance
        if not order:
            return
        attr = 'pickup_geofence_entered' if order.status == OrderStatus.PICK_UP else 'geofence_entered'
        if getattr(order, attr) is None and not geofence_entered:
            raise serializers.ValidationError('Cannot mark geofence as exited before entering')
        elif getattr(order, attr) and geofence_entered:
            raise serializers.ValidationError('Geofence has been already marked as entered')
        elif getattr(order, attr) is False:
            raise serializers.ValidationError('Geofence has been already marked as exited')
        return geofence_entered

    def validate(self, attrs):
        attrs = super().validate(attrs)
        geofence_entered, offline_happened_at = attrs.get('geofence_entered'), attrs.get('offline_happened_at')
        self.validate_offline_geofence(geofence_entered, offline_happened_at)

        order = self.instance
        if order.status == OrderStatus.PICK_UP:
            attrs['pickup_geofence_entered'] = attrs.pop('geofence_entered')
        elif order.status == OrderStatus.IN_PROGRESS \
                and order.allow_order_completion_in_geofence(geofence_entered, check_order_status=True):
            attrs['status'] = Order.DELIVERED if not self.instance.merchant.use_way_back_status else Order.WAY_BACK
            attrs['is_completed_by_geofence'] = True

        return attrs

    def validate_offline_geofence(self, geofence_entered, offline_happened_at):
        if not offline_happened_at:
            return

        filter_params = {
            OrderStatus.PICK_UP: {
                True: dict(field='status', new_value__in=[Order.ASSIGNED]),
                False: dict(field='pickup_geofence_entered', new_value=True)
            },
            OrderStatus.IN_PROGRESS: {
                True: dict(field='status',
                           new_value__in=[OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP, OrderStatus.ASSIGNED]),
                False: dict(field='geofence_entered', new_value=True)}
        }

        ValidateLaterDoesNotExist(self.instance.events.filter(
            event=Event.CHANGED, **filter_params[self.instance.status][geofence_entered]),
            'happened_at'
        )(offline_happened_at)

    def update(self, instance, validated_data):
        driver = self.context['request'].user
        order = super().update(instance, validated_data)
        if all([validated_data.get('geofence_entered'),
                order.driver_checklist,
                not order.driver_checklist_passed,
                not validated_data.get('changed_in_offline', False)]):
            driver.send_versioned_push(ChecklistMessage(self.instance))
        return order
