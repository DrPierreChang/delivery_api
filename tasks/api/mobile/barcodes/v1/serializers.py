from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from reporting.context_managers import track_fields_on_change
from tasks.mixins.order_status import OrderStatus
from tasks.models import Barcode, ConcatenatedOrder, Order

from ...customers.v1.serializers import CustomerSerializer
from ...driver_orders.v1.serializers import BarcodeSerializer, OrderLocationSerializer, RODetailsSerializer


class CommentBarcodeSerializer(BarcodeSerializer):
    class Meta(BarcodeSerializer.Meta):
        editable_fields = {'comment'}
        read_only_fields = list(set(BarcodeSerializer.Meta.fields) - set(editable_fields))


class StatisticsBarcodeSerializer(RadaroMobileModelSerializer):
    server_entity_id = serializers.IntegerField(source='id', read_only=True)
    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializer()
    pickup_address = OrderLocationSerializer()
    barcodes = BarcodeSerializer(many=True, source='aggregated_barcodes')
    content_type = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()
    ro_details = RODetailsSerializer(source='route_optimisation_details', read_only=True)

    class Meta:
        model = Order
        fields = (
            'server_entity_id', 'title', 'status', 'customer', 'deliver_address', 'deliver_after', 'deliver_before',
            'pickup_address', 'content_type', 'orders_count', 'barcodes', 'ro_details',
        )

    def get_content_type(self, instance):
        if instance.is_concatenated_order:
            return ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False).model
        else:
            return ContentType.objects.get_for_model(Order, for_concrete_model=False).model

    def get_orders_count(self, instance):
        if not instance.is_concatenated_order:
            return None
        else:
            return len(instance.orders.all())


class StatisticsCountsSerializer(serializers.Serializer):
    barcodes_count = serializers.IntegerField()
    scanned_at_the_warehouse_barcodes_count = serializers.IntegerField()
    scanned_upon_delivery_barcodes_count = serializers.IntegerField()
    orders_count = serializers.IntegerField()
    scanned_at_the_warehouse_orders_count = serializers.IntegerField()
    scanned_upon_delivery_orders_count = serializers.IntegerField()

    def to_representation(self, instance):
        barcodes_count = 0
        scanned_at_the_warehouse_barcodes_count = 0
        scanned_upon_delivery_barcodes_count = 0

        orders_count = 0
        scanned_at_the_warehouse_orders_count = 0
        scanned_upon_delivery_orders_count = 0

        for order in instance:
            barcodes = order.aggregated_barcodes

            barcodes_count += len(barcodes)
            scanned_at_the_warehouse_barcodes_count += sum(1 for b in barcodes if b.scanned_at_the_warehouse)
            scanned_upon_delivery_barcodes_count += sum(1 for b in barcodes if b.scanned_upon_delivery)

            orders_count += 1
            if all(b.scanned_at_the_warehouse for b in barcodes):
                scanned_at_the_warehouse_orders_count += 1
            if all(b.scanned_upon_delivery for b in barcodes):
                scanned_upon_delivery_orders_count += 1

        data = {
            'barcodes_count': barcodes_count,
            'scanned_at_the_warehouse_barcodes_count': scanned_at_the_warehouse_barcodes_count,
            'scanned_upon_delivery_barcodes_count': scanned_upon_delivery_barcodes_count,
            'orders_count': orders_count,
            'scanned_at_the_warehouse_orders_count': scanned_at_the_warehouse_orders_count,
            'scanned_upon_delivery_orders_count': scanned_upon_delivery_orders_count,
        }
        return super().to_representation(data)


class StatisticsSerializer(serializers.Serializer):
    statistics = StatisticsCountsSerializer(source='*')
    orders = StatisticsBarcodeSerializer(source='*', many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        merchant = self.context['request'].user.current_merchant
        if not merchant.enable_barcode_before_delivery:
            self.fields['statistics'].fields.pop('scanned_at_the_warehouse_barcodes_count')
            self.fields['statistics'].fields.pop('scanned_at_the_warehouse_orders_count')
        if not merchant.enable_barcode_after_delivery:
            self.fields['statistics'].fields.pop('scanned_upon_delivery_barcodes_count')
            self.fields['statistics'].fields.pop('scanned_upon_delivery_orders_count')


class ScanBarcodeSerializer(serializers.Serializer):
    barcode_code = serializers.CharField(source='barcode')

    def validate_barcode_code(self, code):
        barcode_qs = Barcode.objects.merchant_active_barcodes(self.context['request'].user.current_merchant)
        barcode_qs = barcode_qs.filter(
            order__deliver_before__range=self.context['view'].get_today_range(),
        ).select_related('order')
        barcode = barcode_qs.filter(code_data=code).first()

        if barcode is None:
            raise serializers.ValidationError(_('Barcode is not found'), code='invalid_barcode')
        if barcode.order.driver_id != self.context['request'].user.id:
            raise serializers.ValidationError(_('This barcode has not been assigned to you'), code='not_your_barcode')
        if barcode.scanned_upon_delivery and barcode.scanned_at_the_warehouse:
            raise serializers.ValidationError(
                _('The barcode has been already scanned both times'), code='already_scanned_both',
            )

        merchant = self.context['request'].user.current_merchant
        allowed_to_scan_upon_delivery = (
                merchant.enable_barcode_after_delivery
                and barcode.order.status == OrderStatus.IN_PROGRESS
        )
        allowed_to_scan_at_the_warehouse = (
                merchant.enable_barcode_before_delivery
                and (
                        (barcode.order.status == OrderStatus.ASSIGNED and barcode.order.pickup_address_id is None)
                        or (barcode.order.status == OrderStatus.PICK_UP and barcode.order.pickup_address_id is not None)
                )
        )

        # The "elif" construction is used. Be careful when editing
        if allowed_to_scan_upon_delivery:
            if barcode.scanned_upon_delivery:
                raise serializers.ValidationError(
                    _('The barcode has been already scanned upon delivery'), code='already_scanned_upon_delivery',
                )
        elif allowed_to_scan_at_the_warehouse:
            if barcode.scanned_at_the_warehouse:
                raise serializers.ValidationError(
                    _('The barcode has been already scanned at warehouse'), code='already_scanned_at_the_warehouse',
                )
        else:
            raise serializers.ValidationError(
                _('Incorrect job status to scan this barcode'), code='invalid_status_for_scan',
            )

        return barcode

    def scan_barcode(self):
        barcode = self.validated_data['barcode']

        with track_fields_on_change(barcode.order, initiator=self.context['request'].user, sender=self):
            if barcode.order.status == OrderStatus.IN_PROGRESS:
                barcode.scanned_upon_delivery = True
            if barcode.order.status in [OrderStatus.ASSIGNED, OrderStatus.PICK_UP]:
                barcode.scanned_at_the_warehouse = True
            barcode.save()

        return barcode
