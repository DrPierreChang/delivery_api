from rest_framework import serializers

from driver.api.legacy.serializers.driver import DriverSerializer


class DriverField(serializers.PrimaryKeyRelatedField):
    def use_pk_only_optimization(self):
        return False

    def to_representation(self, value):
        exclude_driver_fields = ('email', 'merchant', 'manager', 'location')
        return DriverSerializer(value, context=self.context, exclude_fields=exclude_driver_fields).data
