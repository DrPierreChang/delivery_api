from operator import attrgetter

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.deconstruct import deconstructible

from radaro_utils.descriptors import ModelFieldDescriptor


@deconstructible
class NotNumericSmsSenderValidator:
    message = 'SMS sender name with length more than %(limit_value)s symbols must be numeric'
    code = 'not_numeric_max_length'
    NOT_NUMERIC_LIMIT = 11

    def __call__(self, value):
        if not value.isnumeric() and len(value) > self.NOT_NUMERIC_LIMIT:
            raise ValidationError(self.message, code=self.code, params={'limit_value': self.NOT_NUMERIC_LIMIT})


class SmsSenderField(models.CharField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validators.append(NotNumericSmsSenderValidator())


class MerchantHasRelatedSurveys(ModelFieldDescriptor):
    cache_name = '_has_related_surveys'
    single = True

    def get_foreign_related_value(self, instance):
        # Instance: Dict of 'id'(merchant id) and 'surveys_count'
        return instance['id']

    def get_local_related_value(self, instance):
        # Merchant
        return instance.id

    def get_default_queryset(self):
        from merchant_extension.models import Survey
        return Survey.objects.all()

    def filter_queryset(self, instances, queryset):
        from merchant.models import Merchant
        from merchant_extension.models import Survey
        merchants = set(instances)
        cases = []
        for merchant in merchants:
            surveys_count = Survey.objects.related_for_merchant(merchant).count()
            cases.append(models.When(id=merchant.id, then=surveys_count))
        qs = Merchant.objects.filter(id__in=list(map(attrgetter('id'), instances))) \
            .annotate(surveys_count=models.Case(*cases, default=0, output_field=models.IntegerField())) \
            .values('id', 'surveys_count')
        return qs

    def get_value_by_python(self, instance):
        from merchant_extension.models import Survey
        return {'surveys_count': Survey.objects.related_for_merchant(instance).count(), 'id': instance.id}

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self
        res = super().__get__(instance, instance_type)
        return (res['surveys_count'] > 0) if res else False
