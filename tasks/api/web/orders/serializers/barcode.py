from rest_framework import serializers

from tasks.models import Barcode


class BarcodeListSerializer(serializers.ListSerializer):
    existing_code_data = set()

    def get_existing_code_data(self, barcodes):
        new_code_data = {item['code_data'] for item in barcodes if 'code_data' in item}
        ignore_ids = {item['id'] for item in barcodes if 'id' in item}
        merchant = self.context['request'].user.current_merchant
        active_barcodes = Barcode.objects.merchant_active_barcodes(merchant)
        saved_code_data = active_barcodes.filter(code_data__in=new_code_data).exclude(id__in=ignore_ids)
        return set(saved_code_data.values_list('code_data', flat=True))

    def to_internal_value(self, data):
        self.existing_code_data = self.get_existing_code_data(data)
        return super().to_internal_value(data)

    def create(self, validated_data):
        barcodes = Barcode.objects.bulk_create(Barcode(**barcode_data) for barcode_data in validated_data)
        return barcodes

    def update(self, queryset, validated_data):
        if not validated_data:
            return []

        barcodes_to_remove = []
        barcodes_to_create = []

        for barcode_data in validated_data:
            code_id = barcode_data.pop('id', None)
            if code_id:
                if list(barcode_data.keys()) == ['order']:
                    # Remove barcode if only `id` was provided
                    barcodes_to_remove.append(code_id)
                    continue
                # Update barcode with the new data by id
                queryset.filter(id=code_id).update(**barcode_data)
            else:
                # Create new barcode with the data if `id` was not provided
                barcodes_to_create.append(Barcode(**barcode_data))
        queryset.filter(id__in=barcodes_to_remove).delete()
        queryset.bulk_create(barcodes_to_create)

        return queryset


class BarcodeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if self.root.instance is None:
            attrs.pop('id', None)
        return attrs

    def validate_code_data(self, attr):
        if not attr:
            raise serializers.ValidationError('Barcode is not be empty', code='empty_barcode')
        if attr in self.parent.existing_code_data:
            raise serializers.ValidationError('Barcode {} already exists.'.format(attr), code='non_unique_barcode')
        self.parent.existing_code_data.add(attr)
        return attr

    class Meta:
        model = Barcode
        fields = ('id', 'code_data', 'scanned_upon_delivery', 'scanned_at_the_warehouse', 'required', 'comment')
        read_only_fields = ('scanned_upon_delivery', 'scanned_at_the_warehouse', 'comment')
        list_serializer_class = BarcodeListSerializer
