from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from base.models import Member
from base.utils import MerchantFieldCallControl
from driver.api.legacy.serializers.driver import ListDriverSerializerV2
from tasks.api.web.orders.serializers import WebOrderSerializer
from tasks.api.web.orders.serializers.location import WebLocationSerializer
from tasks.models import Order, OrderLocation


def get_ct(model):
    content_types = ContentType.objects.get_for_models(Member, Order, OrderLocation, for_concrete_models=False)
    return content_types[model]


def get_search_class(model):
    content_types = ContentType.objects.get_for_models(Member, Order, OrderLocation, for_concrete_models=False)
    SEARCH_CLASSES = {
        content_types[Member].model: ListDriverSerializerV2,
        content_types[Order].model: WebOrderSerializer,
        content_types[OrderLocation].model: WebLocationSerializer
    }
    return SEARCH_CLASSES.get(model)


class WebSearchListSerializer(serializers.ListSerializer):
    def prefetch_generic_related(self, instances, ct, queryset):
        search_entries_for_ct = [
            instance for instance in instances
            if instance.content_type_id == ct.id
        ]
        object_ids = [entry.object_id for entry in search_entries_for_ct]
        objects = list(queryset.filter(id__in=object_ids))
        objects = {obj.id: obj for obj in objects}
        for entry in search_entries_for_ct:
            obj = objects.get(entry.object_id_int)
            if obj is not None:
                entry.object = obj

    def to_representation(self, instance):
        member_qs = Member.objects.all().select_related(
            'car', 'starting_hub__location', 'ending_hub__location', 'last_location',
        ).prefetch_related('merchant', 'skill_sets')
        with MerchantFieldCallControl.allow_field_call():
            self.prefetch_generic_related(instance, get_ct(Member), member_qs)
        self.prefetch_generic_related(instance, get_ct(Order), Order.objects.all().prefetch_for_web_api())
        self.prefetch_generic_related(instance, get_ct(OrderLocation), OrderLocation.objects.all())

        return super().to_representation(instance)


class WebSearchSerializer(serializers.Serializer):
    class Meta:
        list_serializer_class = WebSearchListSerializer

    def to_representation(self, instance):
        model = instance.content_type.model
        object_serializer_class = get_search_class(model)

        if object_serializer_class:
            data = object_serializer_class(instance=instance.object, context=self.context).data
            data.update({'content_type': model})
            return data
