from rest_framework import serializers
from rest_framework.relations import MANY_RELATION_KWARGS, ManyRelatedField


class PreloadManyRelatedField(ManyRelatedField):
    preload_items = {}

    def to_internal_value(self, data):
        if isinstance(data, str) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        item_ids = [item for item in data if isinstance(item, int)]
        qs = self.child_relation.get_queryset().filter(id__in=item_ids)
        self.preload_items = {item.id: item for item in qs}

        return [
            self.child_relation.to_internal_value(item)
            for item in data
        ]


class WebPrimaryKeyWithMerchantRelatedField(serializers.PrimaryKeyRelatedField):

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return PreloadManyRelatedField(**list_kwargs)

    def to_internal_value(self, data):
        if hasattr(self.parent, 'preload_items'):
            if not isinstance(data, int):
                self.fail('incorrect_type', data_type=type(data).__name__)
            elif data not in self.parent.preload_items.keys():
                self.fail('does_not_exist', pk_value=data)
            else:
                return self.parent.preload_items[data]
        else:
            return super().to_internal_value(data)

    def get_queryset(self):
        merchant_id = self.context['request'].user.current_merchant_id
        return super().get_queryset().filter(merchant_id=merchant_id)
