from __future__ import absolute_import, unicode_literals

import re

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.utils.serializer_helpers import ReturnList

from tasks.api.legacy.serializers.bulk import (
    OrderPrototypeChunkSerializer,
    OrderPrototypeListSerializer,
    OrderPrototypeSerializer,
)
from tasks.api.legacy.serializers.external_orders import ExternalJobSerializer, NonUniqueExternalIDException
from tasks.models.bulk import BulkDelayedUpload
from tasks.models.bulk_serializer_mapping import prototype_serializers
from tasks.models.external import ExternalJob

from .external_orders import ExternalJobRelatedField, OrderFromExternalJobSerializer


class WebhookExternalJobSerializer(ExternalJobSerializer):
    source = ExternalJobRelatedField(read_only=True)

    def to_internal_value(self, data):
        internal_data = data
        if data is not None:
            internal_data = {
                'external_id': data,
                'source_id': self.parent.context['source_id'],
                'source_type': self.parent.context['source_type_id']
            }
        return super(WebhookExternalJobSerializer, self).to_internal_value(internal_data)

    def validate_external_id(self, attr):
        if not attr:
            raise serializers.ValidationError("External id can't be blank.")
        if re.match(r'^\.[\w.\-\~]*', attr):
            raise ValidationError("External id can't contain '.' at the beginning")
        if attr in self.parent.external_ids:
            raise NonUniqueExternalIDException('External id {} in orders list is not unique.'.format(attr))
        else:
            self.parent.external_ids.add(attr)
        return attr


class ExternalOrderPrototypeSerializer(OrderPrototypeSerializer):
    content = OrderFromExternalJobSerializer()
    external_id = WebhookExternalJobSerializer(required=True, source='external_job')

    def to_internal_value(self, data):
        _data = {
            'content': data
        }
        try:
            _external_id = data.pop('external_id', False)
            if _external_id is not False:
                _data['external_id'] = _external_id
            delivery_interval = _data['content'].pop('delivery_interval', None)
            if delivery_interval:
                _data['content'].update({
                    'deliver_after': delivery_interval['lower'],
                    'deliver_before': delivery_interval['upper']
                })
            _data = super(ExternalOrderPrototypeSerializer, self).to_internal_value(_data)
            driver = _data['content'].pop('driver', None)
            if driver:
                _data['content']['driver'] = driver.id
            if driver and not self.parent.context['merchant_id']:
                _data['content']['merchant'] = driver.current_merchant_id
            skill_sets = _data['content'].pop('skill_sets', None)
            if skill_sets:
                _data['content']['skill_sets'] = list(map(lambda obj: getattr(obj, 'id'), skill_sets))
            skids = _data['content'].pop('skids', None)
            if skids:
                _data['content']['cargoes'] = {}
                _data['content']['cargoes']['skids'] = [
                    {
                        'name': skid['name'],
                        'quantity': skid['quantity'],
                        'weight': {
                            'value': skid['weight'],
                            'unit': skid['weight_unit'],
                        },
                        'sizes': {
                            'width': skid['width'],
                            'height': skid['height'],
                            'length': skid['length'],
                            'unit': skid['sizes_unit'],
                        },
                    }
                    for skid in skids
                ]

            return _data
        except serializers.ValidationError as vex:
            content = vex.detail.pop('content', False)
            if content:
                vex.detail.update(content)
            external = vex.detail.get('external_id', False)
            if not isinstance(external, list) and external is not False:
                del vex.detail['external_id']
                vex.detail.update(external)
            vex.detail['passed_external_id'] = _data['external_id'] if 'external_id' in _data else None
            raise


class ExternalOrderPrototypeListSerializer(OrderPrototypeListSerializer):
    raise_exception = False

    child = ExternalOrderPrototypeSerializer()

    # We raise errors if chunk is not valid, so here we have all validated data, including external_job
    def create(self, validated_data):
        ext_jobs = {}
        for ind, op in enumerate(validated_data):
            ext_job_data = op.pop('external_job', False)
            if ext_job_data is not False:
                ext_jobs[ind] = ExternalJob(**ext_job_data)
        if ext_jobs:
            ExternalJob.objects.bulk_create(ext_jobs.values())
        for ind in ext_jobs:
            validated_data[ind]['external_job'] = ext_jobs[ind]
        return super(ExternalOrderPrototypeListSerializer, self).create(validated_data)


class ExternalOrderPrototypeChunkSerializer(OrderPrototypeChunkSerializer):
    bulk_serializer_class = ExternalOrderPrototypeListSerializer

    @property
    def context(self):
        base_context = super(ExternalOrderPrototypeChunkSerializer, self).context
        request = base_context['request']
        source_type = ContentType.objects.get_for_model(type(request.auth))
        _context = {
            'source_id': request.auth.id,
            'source_type_id': source_type.id,
            'merchant_id': request.auth.merchant.id if request.auth.merchant else None
        }
        context = dict(base_context, **_context)
        return context

    def validate_and_save(self, bulk=None, *args, **kwargs):
        context = self.context
        ind = 0
        try:
            with transaction.atomic():
                if not bulk:
                    bulk = BulkDelayedUpload.objects.create(method=BulkDelayedUpload.EXTERNAL_API,
                                                            creator=context['request'].auth.creator,
                                                            merchant_id=context['merchant_id'],
                                                            status=BulkDelayedUpload.COMPLETED,
                                                            unpack_serializer=prototype_serializers.EXTERNAL)
                for bulk_serializer in self.validate_in_chunks():
                    bulk_serializer.save(bulk=bulk)
                    ind += 1
                bulk.update_state()
                if bulk._stats['errors_found']:
                    errors = bulk.prototypes.order_by('id').only('errors')
                    raise ValidationError(ReturnList([err.errors if err.errors else {} for err in errors], serializer=self))
                bulk.save()
            return bulk
        except NonUniqueExternalIDException as nex:
            raise serializers.ValidationError({'non_field_errors': [nex.message]})
