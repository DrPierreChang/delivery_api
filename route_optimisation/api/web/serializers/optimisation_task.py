from rest_framework import serializers

from route_optimisation.api.web.serializers.route_optimisation import RouteOptimisationSerializer
from route_optimisation.models import OptimisationTask


class OptimisationTaskSerializer(serializers.ModelSerializer):
    optimisation = RouteOptimisationSerializer()

    class Meta:
        model = OptimisationTask
        fields = serializers.ALL_FIELDS
