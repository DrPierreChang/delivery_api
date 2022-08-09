from __future__ import unicode_literals

import copy

from django.conf import settings

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField
from rest_framework.settings import api_settings
from rest_framework.utils import html

from radaro_utils import helpers
from tasks.models import Order
from tasks.models.bulk import OrderPrototype


# Modifying of original method, to store collected errors and valid data
class MemorizingListSerializer(serializers.ListSerializer):
    list_errors = None
    raise_exception = False

    # Modified original method to keep errors for future re-use
    def to_internal_value(self, data):
        """
        List of dicts of native values <- List of dicts of primitive datatypes.
        """
        if html.is_html_input(data):
            data = html.parse_html_list(data)

        if not isinstance(data, list):
            message = self.error_messages['not_a_list'].format(
                input_type=type(data).__name__
            )
            raise ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='not_a_list')

        if not self.allow_empty and len(data) == 0:
            if self.parent and self.partial:
                raise SkipField()

            message = self.error_messages['empty']
            raise ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='empty')

        list_ret = []
        self.list_errors = []

        for item in data:
            try:
                validated = self.child.run_validation(item)
            except ValidationError as exc:
                self.list_errors.append(exc.detail)
            else:
                list_ret.append(validated)
                self.list_errors.append({})

        if self.raise_exception and any(self.list_errors):
            raise ValidationError(self.list_errors)

        return list_ret

    def is_valid(self, raise_exception=False):
        self.raise_exception = raise_exception
        return super(MemorizingListSerializer, self).is_valid(raise_exception)


class RestoreSerializer(MemorizingListSerializer):
    _initial_data = []

    @property
    def initial_data(self):
        return self._initial_data

    @initial_data.setter
    def initial_data(self, val):
        self._initial_data = list(val)

    def to_internal_value(self, data):
        """
        List of dicts of native values <- List of dicts of primitive datatypes.
        """
        if not self.allow_empty and len(data) == 0:
            if self.parent and self.partial:
                raise SkipField()

            message = self.error_messages['empty']
            raise ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='empty')

        list_ret = []
        self.list_errors = []

        for item in data:
            try:
                validated = self.child.run_validation(item.content)
            except ValidationError as exc:
                self.list_errors.append(exc.detail)
            else:
                list_ret.append(validated)
                self.list_errors.append({})

        if self.raise_exception and any(self.list_errors):
            raise ValidationError(self.list_errors)

        return list_ret


class OrderRestoreSerializer(RestoreSerializer):
    m2m_relations = ('skill_sets', 'labels')

    def create_orders(self, **kwargs):
        chunk_size = settings.ORDER_SAVE_BATCH_SIZE
        bulk = kwargs['bulk']
        orders = []
        barcodes_list, skids_list = [], []
        m2m_relations_map = {rel: [] for rel in self.m2m_relations}

        for index, item in enumerate(self.validated_data):
            data = dict(item, model_prototype=self.initial_data[index], **kwargs)
            if bulk.merchant_id:
                data['merchant'] = bulk.merchant
            if data['model_prototype'].external_job_id:
                data['external_job_id'] = data['model_prototype'].external_job_id
            order_relation_map = {rel: data.pop(rel) for rel in self.m2m_relations if rel in data}
            barcodes_list.append(data.pop('barcodes', []))
            skids_list.append(data.pop('skids', []))
            order = Order(**data)
            orders.append(order)

            for rel, rel_value in order_relation_map.items():
                m2m_relations_map[rel].append((order, rel_value))

        created_orders = []
        for chunk_orders in helpers.chunks(orders, n=chunk_size):
            created_orders += Order.objects.create_in_bulk(chunk_orders) if bulk.merchant_id \
                else Order.objects.create_in_mixed_bulk(chunk_orders)

        self._process_m2m_relations(m2m_relations_map)

        for index, order in enumerate(created_orders):
            self.initial_data[index].mark_as_ready(save=False)
            order.barcodes.set(barcodes_list[index], bulk=False)
            order.skids.set(skids_list[index], bulk=False)
        return created_orders

    @staticmethod
    def _process_m2m_relations(m2m_relations_map):
        for relation, related_objects_list in m2m_relations_map.items():
            m2m_field = getattr(Order, relation)
            m2m_field_name = m2m_field.rel.field.m2m_reverse_field_name()
            M2MThroughModel = m2m_field.through

            def _bulk_relation_generator(related_objects_list, m2m_model):
                for item in related_objects_list:
                    order, relations_list = item
                    relations_list = {item.id: item for item in relations_list}
                    # In relations_list it is important that there are no repetitive items.
                    for rel_obj in relations_list.values():
                        yield m2m_model(order=order, **{m2m_field_name: rel_obj})

            M2MThroughModel.objects.bulk_create(
                _bulk_relation_generator(related_objects_list, M2MThroughModel)
            )


class OrderPrototypeSerializer(serializers.ModelSerializer):

    @property
    def external_ids(self):
        return self.parent.external_ids

    class Meta:
        model = OrderPrototype
        fields = '__all__'
        read_only_fields = ('created', 'modified', 'bulk')


class OrderPrototypeListSerializer(MemorizingListSerializer):
    child = OrderPrototypeSerializer()

    _external_ids = None
    _save_kwargs = None

    @property
    def external_ids(self):
        return self._external_ids

    @external_ids.setter
    def external_ids(self, val):
        self._external_ids = val

    def __init__(self, *args, **kwargs):
        super(OrderPrototypeListSerializer, self).__init__(*args, **kwargs)

    # To accumulate external ids and differ external id duplicates in request and in DB
    def set_external_ids(self, _external_ids):
        self._external_ids = _external_ids

    @property
    def validated_data(self):
        if not hasattr(self, '_validated_data'):
            msg = 'You must call `.is_valid()` before accessing `.validated_data`.'
            raise AssertionError(msg)
        else:
            if not hasattr(self, '_all_validated_data'):
                self._all_validated_data = []
                data_ind = 0
                ln_snc = self.context['line_since']
                if ln_snc:
                    errors = zip(range(ln_snc, len(self.list_errors) + ln_snc), self.list_errors)
                else:
                    errors = enumerate(self.list_errors)
                for ind, err in errors:
                    if err:
                        data = {'errors': err.pop('content', err)}
                    else:
                        data = self._validated_data[data_ind]
                        data_ind += 1
                    self._all_validated_data.append(dict(data, line=ind))
            return self._all_validated_data

    def create(self, validated_data):
        data_to_save = [OrderPrototype(**v) for v in validated_data]
        return OrderPrototype.objects.bulk_create(data_to_save)


class OrderPrototypeChunkSerializer(serializers.Serializer):
    raise_exception = False

    bulk_serializer_class = OrderPrototypeListSerializer

    # Silenced as it desirable not to store chunks and save them right after validation
    def is_valid(self, raise_exception=False):
        assert hasattr(self, 'initial_data'), (
            'Cannot call `.is_valid()` as no `data=` keyword argument was '
            'passed when instantiating the serializer instance.'
        )
        if isinstance(self.initial_data, dict):
            self.initial_data = [self.initial_data]

    def __init__(self, *args, **kwargs):
        super(OrderPrototypeChunkSerializer, self).__init__(*args, **kwargs)
        self._external_ids = set()
        self.chunk_size = settings.BULK_JOB_CREATION_BATCH_SIZE

    def get_serializer(self, chunk_data, line_since):
        bulk_serializer = self.bulk_serializer_class(data=chunk_data, allow_empty=False,
                                                     context=dict(self.context, line_since=line_since))
        bulk_serializer.external_ids = self._external_ids
        bulk_serializer.is_valid(raise_exception=self.raise_exception)
        self._external_ids = bulk_serializer.external_ids
        return bulk_serializer

    def data_chunks(self, chunk_size, data_len):
        return helpers.chunks(copy.deepcopy(self.initial_data), chunk_size, length=data_len)

    def validate_in_chunks(self, chunk_size=None, line_since=0):
        data_len = len(self.initial_data)
        chunk_size = chunk_size or self.chunk_size
        for chunk in self.data_chunks(chunk_size, data_len):
            yield self.get_serializer(list(chunk), line_since)
