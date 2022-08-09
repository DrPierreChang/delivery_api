from django.db import models

from rest_framework import serializers

from tasks.models import SKID, Order

from .base import OrderSkidSerializer


class ManagerOrderSkidListSerializer(serializers.ListSerializer):

    def validate(self, attrs):
        order = self.root.instance
        if order:
            exist_ids = set(self.root.instance.skids.values_list('id', flat=True))
        else:
            exist_ids = set()

        new_ids = {attr['id'] for attr in attrs if 'id' in attr}
        invalid_ids = new_ids - exist_ids

        if invalid_ids:
            raise serializers.ValidationError('IDs {} do not exist'.format(', '.join(map(str, invalid_ids))))

        return super().validate(attrs)


class ManagerOrderSkidSerializer(OrderSkidSerializer):
    id = serializers.IntegerField(required=False)

    class Meta(OrderSkidSerializer.Meta):
        list_serializer_class = ManagerOrderSkidListSerializer
        fields = ('id', 'name', 'quantity', 'weight', 'sizes', 'driver_changes', 'original_skid')
        extra_kwargs = {
            'driver_changes': {'read_only': True},
            'original_skid': {'read_only': True},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if 'id' in attrs.keys():
            return attrs

        skid_fields = {'name', 'quantity', 'weight', 'weight_unit', 'width', 'height', 'length', 'sizes_unit'}
        if skid_fields - set(attrs.keys()):
            raise serializers.ValidationError('For creating a new SKID all fields are required')
        return attrs


class ManagerOrderCargoes(serializers.ModelSerializer):
    skids = ManagerOrderSkidSerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = ('skids',)

    def validate_skids(self, attr):
        user = self.context.get('request').user
        if not user.current_merchant.enable_skids:
            raise serializers.ValidationError('SKIDs are not enabled for your merchant, '
                                              'please contact the administrator.')
        return attr


class OrderCargoesMixin(serializers.ModelSerializer):

    def update(self, instance, validated_data):
        skids = validated_data.pop('skids', [])
        if not skids:
            return super().update(instance, validated_data)

        skids_to_remove = []
        skids_to_create = []

        for data in skids:
            skid_id = data.pop('id', None)
            if skid_id:
                if not data:
                    # Remove SKID if only `id` was provided
                    skids_to_remove.append(skid_id)
                    continue
                # Update SKID with the new data by id
                instance.skids.filter(id=skid_id).update(**data, driver_changes=None, original_skid=None)
            else:
                # Create new SKID with the data if `id` was not provided
                skids_to_create.append(SKID(order=instance, **data, driver_changes=None, original_skid=None))
        instance.skids.filter(id__in=skids_to_remove).delete()
        SKID.objects.bulk_create(skids_to_create)

        return super().update(instance, validated_data)

    def create(self, validated_data):
        skids = validated_data.pop('skids', [])
        for skid in skids:
            skid.pop('id', None)

        order = super().create(validated_data)

        SKID.objects.bulk_create(SKID(order=order, **skid) for skid in skids)
        return order
