from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from base.api.legacy.serializers.fields import MemberIDDriverField
from merchant.models import Hub
from merchant.validators import MerchantsOwnValidator
from route_optimisation.api.fields import CurrentMerchantDefault
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from route_optimisation.models import DriverRoute, OptimisationTask, RouteOptimisation, RoutePoint
from tasks.models import Order


class ExternalRoutePointSerializer(serializers.ModelSerializer):
    point_type_map = dict(hub=Hub, order=Order)
    point_kind_map = dict(hub=RoutePointKind.HUB, order=RoutePointKind.DELIVERY)

    point_content_type = serializers.ChoiceField(choices=tuple(point_type_map.keys()))
    point_object_external_id = serializers.CharField(required=False)

    class Meta:
        model = RoutePoint
        fields = ('point_content_type', 'point_object_id', 'point_object_external_id', 'number',
                  'start_time', 'end_time', 'service_time',)
        extra_kwargs = {'number': {'required': True}}

    def validate(self, attrs):
        type_from_attrs = attrs['point_content_type']
        content_type = ContentType.objects.get_for_model(self.point_type_map[type_from_attrs])
        attrs['point_content_type'] = content_type
        attrs['point_kind'] = self.point_kind_map[type_from_attrs]

        external_id, object_id = attrs.pop('point_object_external_id', None), attrs.get('point_object_id')
        if not (external_id or object_id):
            raise serializers.ValidationError("One of fields 'point_object_id' or 'point_object_external_id' "
                                              "must be passed.")
        id_field = {}
        if object_id:
            id_field['id'] = object_id
        else:
            id_field['external_job_id__external_id'] = external_id

        merchant = self.context['request'].user.current_merchant
        try:
            obj = content_type.get_object_for_this_type(merchant=merchant, **id_field)
            attrs['point_object_id'] = obj.id
        except content_type.model_class().DoesNotExist:
            raise serializers.ValidationError('Object with id %s for content_type %s does not exist'
                                              % (object_id or external_id, content_type))
        return attrs


class ExternalDriverRouteSerializer(serializers.ModelSerializer):
    route_points = ExternalRoutePointSerializer(many=True)
    driver = MemberIDDriverField(validators=[MerchantsOwnValidator('driver', merchant_field='current_merchant')])

    class Meta:
        model = DriverRoute
        fields = ('id', 'driver', 'route_points', 'start_time', 'end_time', )

    def validate(self, attrs):
        if not attrs.get('start_time') and attrs['route_points']:
            attrs['start_time'] = min(point['start_time'] for point in attrs['route_points'])

        if not attrs.get('end_time') and attrs['route_points']:
            attrs['end_time'] = max(point['end_time'] for point in attrs['route_points'])

        if attrs.get('total_time') is None:
            if attrs.get('start_time') and attrs.get('end_time'):
                attrs['total_time'] = int((attrs['end_time'] - attrs['start_time']).total_seconds())
            else:
                attrs['total_time'] = 0

        if attrs.get('driving_time') is None:
            if attrs.get('total_time') and attrs['route_points']:
                service_time = sum(point.get('service_time', 0) for point in attrs['route_points'])
                attrs['driving_time'] = attrs['total_time'] - service_time
            else:
                attrs['driving_time'] = 0

        if not attrs.get('driving_distance') and attrs['route_points']:
            attrs['driving_distance'] = 0

        return attrs


class ExternalRouteOptimisationSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    type = serializers.HiddenField(default=OPTIMISATION_TYPES.PTV_EXPORT)

    days = serializers.ListField(child=serializers.DateField(), required=False, write_only=True)
    driver_routes = ExternalDriverRouteSerializer(many=True, required=True, write_only=True)

    class Meta:
        model = RouteOptimisation
        fields = ('id', 'type', 'day', 'days', 'driver_routes', 'merchant', 'created_by', 'options', )
        extra_kwargs = {'day': {'required': False}}

    def validate(self, attrs):
        if 'day' not in attrs:
            if 'days' not in attrs:
                raise serializers.ValidationError('day or days field should be passed')
            attrs['day'] = attrs.pop('days')[0]
        return super().validate(attrs)

    def create(self, validated_data):
        driver_routes = validated_data.pop('driver_routes', [])
        instance = super().create(validated_data)
        task, _ = OptimisationTask.objects.get_or_create(optimisation=instance)
        task.begin()
        task.save(update_fields=('status',))
        instance.backend.on_create({'driver_routes': driver_routes}, serializer_context=self.context)
        return instance
