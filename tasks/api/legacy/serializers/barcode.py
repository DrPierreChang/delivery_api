from django.db.models import Q

from rest_framework import serializers

from pandas.io import json
from rest_framework_bulk import BulkListSerializer, BulkSerializerMixin

from reporting.context_managers import track_fields_on_change
from tasks.models import Barcode, Order


class BarcodeField(serializers.ListField):
    child = serializers.DictField()

    def to_internal_value(self, data):
        try:
            data = json.loads(data)
        except ValueError:
            raise serializers.ValidationError("Incorrect value is provided.")
        return data


class BarcodeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, read_only=False)
    scanned = serializers.BooleanField(required=False)

    class Meta:
        model = Barcode
        exclude = ('order',)

    def validate_code_data(self, attr):
        if attr in self.parent.existing_code_data:
            raise serializers.ValidationError('Barcode {} already exists.'.format(attr))
        self.parent.existing_code_data.add(attr)
        return attr

    def validate(self, attrs):
        scanned = attrs.pop('scanned', None)
        if self.instance and scanned:
            scanned_field = self.instance.get_scanned_field()
            if scanned_field:
                attrs[scanned_field] = scanned

        return attrs


class BarcodeListSerializer(serializers.ListSerializer):
    child = BarcodeSerializer()

    existing_code_data = set()

    def get_existing_code_data(self, barcodes):
        # All code_data options available in the request are collected here
        new_code_data = {item['code_data'] for item in barcodes if 'code_data' in item}

        # Here the identifiers of all barcodes whose code_data will be changed are collected
        # The code_data stored in the database that will be changed
        # will not be used to verify the uniqueness of the new code_data
        # Details are in BarcodesUnpackMixin.update
        ids_edited_barcodes = {item['id'] for item in barcodes
                               if 'id' in item and ('code_data' in item or len(item) == 1)}

        active_barcodes = Barcode.objects.merchant_active_barcodes(self.context['request'].user.current_merchant)
        saved_code_data = active_barcodes.exclude(id__in=ids_edited_barcodes).filter(code_data__in=new_code_data)
        return set(saved_code_data.values_list('code_data', flat=True))

    def to_internal_value(self, data):
        self.existing_code_data = self.get_existing_code_data(data)
        return super().to_internal_value(data)

    def validate(self, attrs):
        ids_edited_barcodes = {item['id'] for item in attrs if 'id' in item}
        active_barcodes = Barcode.objects.merchant_active_barcodes(self.context['request'].user.current_merchant)
        existed_barcodes = active_barcodes.filter(id__in=ids_edited_barcodes)
        ids_existed_barcodes = set(existed_barcodes.values_list('id', flat=True))
        ids_not_existed_barcodes = ids_edited_barcodes - ids_existed_barcodes
        if ids_not_existed_barcodes:
            raise serializers.ValidationError(
                f'Barcodes with ids {", ".join(map(str, ids_not_existed_barcodes))} do not exist.'
            )
        return attrs


class ScanningBarcodeSerializer(BulkSerializerMixin, serializers.ModelSerializer):
    changed_in_offline = serializers.BooleanField(required=False, write_only=True)
    scanned = serializers.BooleanField(required=False)

    class Meta:
        model = Barcode
        fields = (
            'id', 'code_data', 'scanned_upon_delivery', 'scanned_at_the_warehouse',
            'scanned', 'required', 'changed_in_offline',
        )
        read_only_fields = ('required', 'code_data')
        list_serializer_class = BulkListSerializer

    def update(self, instance, validated_data):
        if validated_data.pop('changed_in_offline', None) and not instance.order.changed_in_offline:
            instance.order.changed_in_offline = True
            instance.order.save(update_fields=('changed_in_offline',))
        return super().update(instance, validated_data)


class ScanningBarcodeBeforeDelivery(ScanningBarcodeSerializer):
    class Meta(ScanningBarcodeSerializer.Meta):
        read_only_fields = ('required', 'code_data', 'scanned_upon_delivery')


class ScanningBarcodeAfterDelivery(ScanningBarcodeSerializer):
    class Meta(ScanningBarcodeSerializer.Meta):
        read_only_fields = ('required', 'code_data', 'scanned_at_the_warehouse')


class ScanningBarcodeBeforeAndAfterDelivery(ScanningBarcodeSerializer):
    class Meta(ScanningBarcodeSerializer.Meta):
        read_only_fields = ('required', 'code_data', 'scanned_upon_delivery', 'scanned_at_the_warehouse')


class ScanBarcodesCodeDataSerializer(serializers.Serializer):
    barcodes = serializers.ListField(child=serializers.CharField())
    changed_in_offline = serializers.BooleanField(write_only=True, required=False)

    def confirm_barcode_scan(self, driver):
        barcodes = self.validated_data['barcodes']
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
            barcodes__code_data__in=barcodes,
        ).distinct()

        if orders:
            order_ids = orders.values_list('id', flat=True)
            with track_fields_on_change(list(orders), initiator=self.context['request'].user):
                barcodes = Barcode.objects.filter(code_data__in=barcodes, order_id__in=order_ids)
                barcodes = barcodes.merchant_active_barcodes(merchant)
                if merchant.enable_barcode_before_delivery:
                    barcodes.confirm_scan_before_delivery()
                if merchant.enable_barcode_after_delivery:
                    barcodes.confirm_scan_after_delivery()

        if self.validated_data.get('changed_in_offline'):
            orders.update(changed_in_offline=True)

        return orders
