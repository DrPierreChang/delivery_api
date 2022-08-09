from django.db.models import Prefetch, Q
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from rest_framework_bulk import BulkSerializerMixin

from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer
from reporting.context_managers import track_fields_on_change
from tasks.models import Barcode, Order


class BarcodeListSerializer(RadaroMobileListSerializer):
    existing_code_data = set()

    def get_existing_code_data(self, barcodes):
        new_code_data = {item['code_data'] for item in barcodes if 'code_data' in item}
        merchant = self.context['request'].user.current_merchant
        saved_code_data = Barcode.objects.merchant_active_barcodes(merchant).filter(code_data__in=new_code_data)
        return set(saved_code_data.values_list('code_data', flat=True))

    def to_internal_value(self, data):
        self.existing_code_data = self.get_existing_code_data(data)
        return super().to_internal_value(data)


class BarcodeSerializer(BulkSerializerMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, read_only=False)

    def validate_code_data(self, attr):
        if attr in self.parent.existing_code_data:
            raise serializers.ValidationError(_('Barcode {code} already exists.').format(code=attr),
                                              code='non_unique_barcode')
        self.parent.existing_code_data.add(attr)
        return attr

    class Meta:
        model = Barcode
        fields = ('id', 'code_data', 'scanned_upon_delivery', 'scanned_at_the_warehouse', 'required', 'comment')
        editable_fields = {'code_data', 'required'}
        read_only_fields = list(set(fields) - set(editable_fields))
        list_serializer_class = BarcodeListSerializer


class ScanBarcodesSerializer(serializers.Serializer):
    barcode_codes = serializers.ListField(child=serializers.CharField(), write_only=True)
    changed_in_offline = serializers.BooleanField(write_only=True, required=False)

    def scan_barcode_one_order(self):
        codes = self.validated_data['barcode_codes']
        instance = self.instance

        if codes:
            if instance.status in (Order.ASSIGNED, Order.PICK_UP):
                instance.barcodes.filter(code_data__in=codes).update(scanned_at_the_warehouse=True)
            if instance.status == Order.IN_PROGRESS:
                instance.barcodes.filter(code_data__in=codes).update(scanned_upon_delivery=True)
            instance._prefetched_objects_cache.pop('barcodes', None)

        if self.validated_data.get('changed_in_offline'):
            instance.changed_in_offline = True
            instance.save()

        return instance

    def scan_barcode_multiple_orders(self, driver):
        codes = self.validated_data['barcode_codes']
        merchant = driver.current_merchant

        status_filter = Q()
        if merchant.enable_barcode_before_delivery:
            status_filter |= Q(status=Order.PICK_UP, pickup_address__isnull=False)
            status_filter |= Q(status=Order.ASSIGNED, pickup_address__isnull=True)
        if merchant.enable_barcode_after_delivery:
            status_filter |= Q(status=Order.IN_PROGRESS)

        if not status_filter:
            return []

        orders = Order.objects.filter(
            status_filter,
            merchant=merchant,
            driver=driver,
            barcodes__code_data__in=codes,
        ).distinct()
        orders = orders.prefetch_related(
            Prefetch('in_driver_route_queue', to_attr=Order.in_driver_route_queue.cache_name),
            Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
        )
        order_ids = orders.values_list('id', flat=True)

        with track_fields_on_change(list(orders), initiator=self.context['request'].user):
            barcodes = Barcode.objects.merchant_active_barcodes(merchant)
            barcodes = barcodes.filter(code_data__in=codes, order_id__in=order_ids)
            if merchant.enable_barcode_before_delivery:
                barcodes.confirm_scan_before_delivery()
            if merchant.enable_barcode_after_delivery:
                barcodes.confirm_scan_after_delivery()

            if self.validated_data.get('changed_in_offline'):
                orders.update(changed_in_offline=True)

        return orders
