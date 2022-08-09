from rest_framework import serializers

from route_optimisation.models import RoutePoint


class CSVRouteOptimisationSerializer(serializers.ModelSerializer):
    driver_id = serializers.IntegerField(source='route__driver__id')
    first_name = serializers.CharField(source='route__driver__first_name')
    last_name = serializers.CharField(source='route__driver__last_name')

    point_type = serializers.CharField(source='point_content_type__model')
    point_type_exact = serializers.CharField(source='point_kind')
    job_sequence_number = serializers.IntegerField(source='number')
    predicted_arrival_time = serializers.TimeField(source='start_time')
    predicted_departure_time = serializers.TimeField(source='end_time')

    order_title = serializers.SerializerMethodField()
    order_id = serializers.SerializerMethodField()
    external_id = serializers.SerializerMethodField()
    pickup_address = serializers.SerializerMethodField()
    pickup_location = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    pickup_after = serializers.SerializerMethodField()
    pickup_before = serializers.SerializerMethodField()
    deliver_after = serializers.SerializerMethodField()
    deliver_before = serializers.SerializerMethodField()

    pickup_name = serializers.SerializerMethodField()
    pickup_phone = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    barcodes = serializers.SerializerMethodField()
    capacity = serializers.SerializerMethodField()

    hub_id = serializers.SerializerMethodField()
    hub_name = serializers.SerializerMethodField()

    class Meta:
        model = RoutePoint
        fields = ('driver_id', 'first_name', 'last_name',
                  'point_type', 'point_type_exact', 'job_sequence_number',
                  'predicted_arrival_time', 'predicted_departure_time',
                  'order_title', 'order_id', 'external_id',
                  'pickup_address', 'pickup_location', 'address', 'location',
                  'pickup_after', 'pickup_before', 'deliver_after', 'deliver_before',
                  'pickup_name', 'pickup_phone', 'customer_name', 'customer_phone',
                  'barcodes', 'capacity', 'hub_id', 'hub_name')
