from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from driver.utils import WorkStatus
from tasks.models import SKID, Order


class OrderSkidWeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('value', 'unit')
        extra_kwargs = {
            'value': {'source': 'weight', 'required': True},
            'unit': {'source': 'weight_unit', 'required': True}
        }


class OrderSkidSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('width', 'height', 'length', 'unit')
        extra_kwargs = {
            'width': {'required': True},
            'height': {'required': True},
            'length': {'required': True},
            'unit': {'source': 'sizes_unit', 'required': True}
        }


class OrderSkidSerializer(serializers.ModelSerializer):
    weight = OrderSkidWeightSerializer(source='*')
    sizes = OrderSkidSizeSerializer(source='*')

    class Meta:
        model = SKID
        fields = ('name', 'quantity', 'weight', 'sizes')


class DriverOrderSkidSerializer(OrderSkidSerializer):
    changed_in_offline = serializers.BooleanField(required=False, write_only=True)
    id = serializers.IntegerField(read_only=True)

    class Meta(OrderSkidSerializer.Meta):
        model = SKID
        fields = ('id', 'name', 'quantity', 'weight', 'sizes', 'changed_in_offline')

    def validate(self, attrs):
        order = self.context['order']

        if order.status != Order.IN_PROGRESS:
            raise serializers.ValidationError(_('Cannot change SKID with current order status'))
        if order.driver.work_status != WorkStatus.WORKING:
            raise serializers.ValidationError(_('Cannot change SKID with current driver status'))
        return attrs

    @staticmethod
    def _changed_in_offline(order):
        if not order.changed_in_offline:
            order.changed_in_offline = True
            order.save(update_fields=('changed_in_offline',))

    def update(self, instance, validated_data):
        if instance.driver_changes == None:
            validated_data['original_skid'] = OrderSkidSerializer(instance).data
        validated_data['driver_changes'] = SKID.EDITED

        if validated_data.pop('changed_in_offline', None):
            self._changed_in_offline(self.context['order'])

        return super().update(instance, validated_data)

    def create(self, validated_data):
        order = self.context['order']
        validated_data['order'] = order
        validated_data['driver_changes'] = SKID.ADDED
        validated_data['original_skid'] = None

        if validated_data.pop('changed_in_offline', None):
            self._changed_in_offline(order)

        return super().create(validated_data)

    def destroy(self):
        if self.instance.driver_changes == None:
            self.instance.original_skid = OrderSkidSerializer(self.instance).data
        self.instance.driver_changes = SKID.DELETED
        self.instance.save()

        if self.validated_data.pop('changed_in_offline', None):
            self._changed_in_offline(self.context['order'])
