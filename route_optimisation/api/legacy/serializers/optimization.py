from rest_framework import serializers

from route_optimisation.models import RouteOptimisation


class LegacyReturnRouteOptimisationSerializer(serializers.ModelSerializer):

    class Meta:
        model = RouteOptimisation
        fields = ('id', )
