import factory


class RoutePointFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'route_optimisation.RoutePoint'


class RouteOptimisationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'route_optimisation.RouteOptimisation'


class OptimisationTaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'route_optimisation.OptimisationTask'


class DriverRouteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'route_optimisation.DriverRoute'


class DriverRouteLocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'route_optimisation.DriverRouteLocation'
