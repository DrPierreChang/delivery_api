import logging

from django.core.exceptions import ObjectDoesNotExist

from rest_framework import serializers
from rest_framework.fields import get_attribute
from rest_framework.relations import MANY_RELATION_KWARGS, ManyRelatedField

from route_optimisation.logging import EventType
from webhooks.models import MerchantAPIKey

logger = logging.getLogger('optimisation')


class empty:
    pass


# TODO: Move to radaro_utils
class PreloadManyRelatedField(ManyRelatedField):
    preload_items = {}

    def to_internal_value(self, data):
        if isinstance(data, str) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        if self.child_relation.pk_field is not None:
            data = [self.child_relation.pk_field.to_internal_value(item) for item in data]

        lookup_field = getattr(self.child_relation, 'lookup_field', 'pk')
        qs = self.child_relation.get_queryset().filter(**{lookup_field + '__in': data})

        lookup_field_attrs = lookup_field.split('__')
        self.preload_items = {get_attribute(item, lookup_field_attrs): item for item in qs}

        result = [
            self.child_relation.to_internal_value(item)
            for item in data
        ]
        return [internal for internal in result if internal is not empty]


class OptimisationPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    # "key == 'validators'" is needed to validate the list of objects
    MANY_RELATION_KWARGS = MANY_RELATION_KWARGS + ('validators', 'allow_null')

    def __init__(self, raise_not_exist=True, lookup_field='pk', **kwargs):
        super().__init__(**kwargs)
        self.raise_not_exist = raise_not_exist
        self.lookup_field = lookup_field

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in OptimisationPrimaryKeyRelatedField.MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return PreloadManyRelatedField(**list_kwargs)

    def _to_internal_value(self, data):
        if self.pk_field is not None:
            data = self.pk_field.to_internal_value(data)
        try:
            return self.get_queryset().get(**{self.lookup_field: data})
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)

    def to_internal_value(self, data):
        if not hasattr(self.parent, 'preload_items'):
            return self._to_internal_value(data)
        if data in self.parent.preload_items.keys():
            return self.parent.preload_items[data]

        if self.optimisation:
            logger.info(
                None,
                extra=dict(
                    obj=self.optimisation, event=EventType.OBJECT_NOT_FOUND,
                    event_kwargs={'model': self.queryset.model._meta.verbose_name, 'obj_id': data,
                                  'lookup_field': self.lookup_field}
                )
            )
        if self.raise_not_exist:
            self.fail('does_not_exist', pk_value=data)
        return empty

    def to_representation(self, value):
        return value.pk

    def get_queryset(self):
        ctx = self.context
        merchant_id = ctx.get('merchant').id if 'merchant' in ctx else ctx['request'].user.current_merchant_id
        return super().get_queryset().filter(merchant_id=merchant_id)

    @property
    def optimisation(self):
        return self.context.get('optimisation')


class ContextMerchantOptimisationPrimaryKeyRelatedField(OptimisationPrimaryKeyRelatedField):
    def get_queryset(self):
        merchant_id = self.context['merchant'].id
        return super(OptimisationPrimaryKeyRelatedField, self).get_queryset().filter(merchant_id=merchant_id)


class ManyMerchantsOptimisationPrimaryKeyRelatedField(OptimisationPrimaryKeyRelatedField):
    def get_queryset(self):
        merchant_api_key = self.context['request'].auth
        if isinstance(merchant_api_key, MerchantAPIKey):
            return super(OptimisationPrimaryKeyRelatedField, self).get_queryset()\
                .filter(merchant_id__in=merchant_api_key.related_merchants)
        return super().get_queryset()
