from rest_framework import serializers

from radaro_utils.serializers.web.fields import WebPrimaryKeyWithMerchantRelatedField
from reporting.context_managers import track_fields_on_change
from tasks.models import ConcatenatedOrder, Order
from tasks.push_notification.push_messages.event_composers import (
    OrderAddedToConcatenatedMessage,
    OrderRemovedFromConcatenatedMessage,
)
from tasks.signal_receivers import co_auto_processing


class AvailableOrdersPrimaryKeyRelatedField(WebPrimaryKeyWithMerchantRelatedField):
    def get_queryset(self):
        return self.root.instance.available_orders


class AddedOrdersConcatenatedOrderSerializer(serializers.ModelSerializer):
    order_ids = AvailableOrdersPrimaryKeyRelatedField(
        many=True, source='orders', queryset=Order.objects.all(), required=True
    )

    class Meta:
        model = ConcatenatedOrder
        fields = ('order_ids',)

    def update(self, instance, validated_data):
        ids = [order.id for order in validated_data['orders']]
        orders = Order.objects.filter(id__in=ids)
        with track_fields_on_change(list(orders), initiator=self.context['request'].user, sender=co_auto_processing):
            orders.update(concatenated_order=instance, driver=instance.driver, status=instance.status)
        instance.update_data()

        if instance.driver:
            for order in validated_data['orders']:
                msg = OrderAddedToConcatenatedMessage(order=order, driver=instance.driver)
                instance.driver.send_versioned_push(msg)

        return instance


class ConcatenatedOrdersPrimaryKeyRelatedField(WebPrimaryKeyWithMerchantRelatedField):
    def get_queryset(self):
        return self.root.instance.orders.all()


class RemoveOrdersConcatenatedOrderSerializer(serializers.ModelSerializer):
    order_ids = ConcatenatedOrdersPrimaryKeyRelatedField(
        many=True, source='orders', queryset=Order.objects.all(), required=True
    )

    class Meta:
        model = ConcatenatedOrder
        fields = ('order_ids',)

    def update(self, instance, validated_data):
        ids = [order.id for order in validated_data['orders']]
        orders = Order.objects.filter(id__in=ids)
        with track_fields_on_change(list(orders), initiator=self.context['request'].user, sender=co_auto_processing):
            orders.update(concatenated_order=None)
        instance.update_data()

        if instance.driver and instance.orders.count() > 0:
            for order in validated_data['orders']:
                msg = OrderRemovedFromConcatenatedMessage(order=order, driver=instance.driver)
                instance.driver.send_versioned_push(msg)

        return instance


class AllAvailableOrdersPrimaryKeyRelatedField(WebPrimaryKeyWithMerchantRelatedField):
    def get_queryset(self):
        return self.root.instance.all_available_orders


class ResetOrdersConcatenatedOrderSerializer(serializers.ModelSerializer):
    order_ids = AllAvailableOrdersPrimaryKeyRelatedField(
        many=True, source='orders', queryset=Order.objects.all(), required=True
    )

    class Meta:
        model = ConcatenatedOrder
        fields = ('order_ids',)

    def update(self, instance, validated_data):
        ids = [order.id for order in validated_data['orders']]

        removed_orders = Order.objects.filter(concatenated_order=instance)
        removed_orders = removed_orders.exclude(id__in=ids).exclude(status=Order.FAILED)
        removed_orders_list = list(removed_orders)

        added_orders = Order.objects.exclude(concatenated_order=instance).filter(id__in=ids)
        added_orders_list = list(added_orders)

        with track_fields_on_change(removed_orders_list + added_orders_list,
                                    initiator=self.context['request'].user,
                                    sender=co_auto_processing):
            removed_orders.update(concatenated_order=None)
            added_orders.update(concatenated_order=instance, driver=instance.driver, status=instance.status)

        instance.update_data()

        if instance.driver and instance.orders.count() > 0:
            for removed_order in removed_orders_list:
                msg = OrderRemovedFromConcatenatedMessage(order=removed_order, driver=instance.driver)
                instance.driver.send_versioned_push(msg)
            for added_order in added_orders_list:
                msg = OrderAddedToConcatenatedMessage(order=added_order, driver=instance.driver)
                instance.driver.send_versioned_push(msg)

        return instance
