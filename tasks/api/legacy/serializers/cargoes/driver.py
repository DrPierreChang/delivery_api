from rest_framework import serializers

from driver.utils import WorkStatus
from tasks.models import SKID, Order

from .base import OrderSkidSerializer


class DriverSkidSerializer(OrderSkidSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta(OrderSkidSerializer.Meta):
        model = SKID
        fields = ('id', 'name', 'quantity', 'weight', 'sizes')


class DriverOrderCargoes(serializers.ModelSerializer):
    skids = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('skids',)

    def get_skids(self, instance):
        if hasattr(instance, 'not_deleted_skids'):
            skids = instance.not_deleted_skids or []
        else:
            skids = instance.skids.all().exclude(driver_changes=SKID.DELETED)
        return DriverSkidSerializer(skids, many=True).data


class DriverOrderSkidSerializer(OrderSkidSerializer):
    changed_in_offline = serializers.BooleanField(required=False, write_only=True)
    id = serializers.IntegerField(read_only=True)

    class Meta(OrderSkidSerializer.Meta):
        model = SKID
        fields = ('id', 'name', 'quantity', 'weight', 'sizes', 'changed_in_offline')

    def validate(self, attrs):
        order = self.context['order']

        if order.status != Order.IN_PROGRESS:
            raise serializers.ValidationError('Cannot change SKID with current order status')
        if order.driver.work_status != WorkStatus.WORKING:
            raise serializers.ValidationError('Cannot change SKID with current driver status')
        return attrs

    def update(self, instance, validated_data):
        if instance.driver_changes == None:
            validated_data['original_skid'] = OrderSkidSerializer(instance).data
        validated_data['driver_changes'] = SKID.EDITED

        order = self.context['order']
        if validated_data.pop('changed_in_offline', None) and not order.changed_in_offline:
            order.changed_in_offline = True
            order.save(update_fields=('changed_in_offline',))
        return super().update(instance, validated_data)

    def create(self, validated_data):
        validated_data['driver_changes'] = SKID.ADDED
        validated_data['original_skid'] = None

        order = self.context['order']
        if validated_data.pop('changed_in_offline', None) and not order.changed_in_offline:
            order.changed_in_offline = True
            order.save(update_fields=('changed_in_offline',))
        validated_data['order'] = order
        return super().create(validated_data)

    def destroy(self):
        if self.instance.driver_changes == None:
            self.instance.original_skid = OrderSkidSerializer(self.instance).data
        self.instance.driver_changes = SKID.DELETED
        self.instance.save()

        order = self.context['order']
        if self.validated_data.pop('changed_in_offline', None) and not order.changed_in_offline:
            order.changed_in_offline = True
            order.save(update_fields=('changed_in_offline',))
