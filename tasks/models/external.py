import operator
import re

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.base import ModelBase
from django.utils import timezone

import six
from model_utils.models import TimeStampedModel
from six.moves import reduce


class ExternalSourceRegisterMetaClass(ModelBase):
    sources = set()

    def __new__(mcs, name, bases, attrs):
        new_cls = super(ExternalSourceRegisterMetaClass, mcs).__new__(mcs, name, bases, attrs)
        mcs.sources.add(new_cls)
        mcs.sources -= set(bases)
        return new_cls


class ExternalSource(six.with_metaclass(ExternalSourceRegisterMetaClass, TimeStampedModel)):
    creator = models.ForeignKey('base.Member', on_delete=models.PROTECT)
    merchant = models.ForeignKey('merchant.Merchant', blank=True, null=True, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class ExternalJobManager(models.Manager):
    def filter_by_merchant(self, merchant):
        source_classes = ContentType.objects.get_for_models(*ExternalSourceRegisterMetaClass.sources)
        query_gen = (Q(source_type=c_type, source_id__in=Model.objects.filter(merchant=merchant))
                     for Model, c_type in source_classes.items())
        return self.get_queryset().filter(reduce(operator.or_, query_gen))


class ExternalJob(models.Model):
    external_id = models.CharField(max_length=250, null=True, blank=True)

    source_id = models.PositiveIntegerField(null=True, blank=True)
    source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.CASCADE)
    source = GenericForeignKey('source_type', 'source_id')

    objects = ExternalJobManager()

    @staticmethod
    def autocomplete_search_fields():
        return 'id__iexact', 'external_id__icontains'

    class Meta:
        unique_together = (('source_type', 'source_id', 'external_id'),)

    def clean(self):
        if re.match(r'^\.[\w.\-\~]*', self.external_id):
            raise ValidationError({
                'external_id': "External id can't contain '.' at the beginning"
            })
        super(ExternalJob, self).clean()

    def safe_delete(self):
        max_length = self._meta.get_field('external_id').max_length
        self.external_id = f'{self.external_id}-deleted-{timezone.now().isoformat()}'[:max_length]
        self.save(update_fields=['external_id'])
