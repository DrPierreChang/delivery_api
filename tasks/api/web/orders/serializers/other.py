from collections import OrderedDict
from itertools import chain

from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from routing.serializers.fields import LatLngLocation
from tasks.models import ConcatenatedOrder, Order

from .customer import CustomerSerializer


class OrderPathSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField()
    path_dict = serializers.DictField(source='path')
    real_path = serializers.SerializerMethodField()
    real_path_dict = serializers.DictField(source='real_path')
    in_progress_point = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'path', 'path_dict', 'real_path', 'real_path_dict', 'in_progress_point')

    def get_path(self, instance):
        if instance.path is None:
            return

        path = OrderedDict(
            (status, instance.path.get(status, []))
            for status in (instance.PICK_UP, instance.IN_PROGRESS, instance.WAY_BACK)
        )
        return list(chain.from_iterable(path.values())) or instance.path.get('full', [])

    def get_real_path(self, instance):
        if instance.real_path is None:
            return

        real_path = OrderedDict(
            (status, instance.real_path.get(status, []))
            for status in (instance.PICK_UP, instance.IN_PROGRESS, instance.WAY_BACK)
        )
        return list(chain.from_iterable(real_path.values())) or instance.real_path.get('full', [])

    def get_in_progress_point(self, instance):
        if instance.in_progress_point:
            return {'location': LatLngLocation().to_representation(instance.in_progress_point)}
        return None


class ContentTypeMixin(serializers.Serializer):
    content_type = serializers.SerializerMethodField()

    def get_content_type(self, instance):
        if instance.is_concatenated_order:
            return ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False).model
        else:
            return ContentType.objects.get_for_model(Order, for_concrete_model=False).model


class CustomerCommentOrderSerializer(ContentTypeMixin, serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ('content_type', 'id', 'customer', 'customer_comment', 'rating', 'updated_at')


class OrderIDSerializer(ContentTypeMixin, serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ('content_type', 'id')


class OrderDeadlineSerializer(ContentTypeMixin, serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ('content_type', 'id', 'deliver_before')
