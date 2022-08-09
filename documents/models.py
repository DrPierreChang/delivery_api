from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.deletion import CASCADE

from base.models import Member
from driver.models import DriverLocation
from merchant.models import Hub, Label, Merchant, SkillSet, SubBranding
from merchant_extension.models import ResultChecklist, SurveyResult
from notification.models import Device, MerchantMessageTemplate
from radaro_utils.files.utils import get_upload_path
from reporting.models import Event


class Tag(models.Model):
    name = models.CharField(max_length=255)
    merchant = models.ForeignKey('merchant.Merchant', on_delete=CASCADE)

    class Meta:
        unique_together = ('name', 'merchant')
        ordering = ('id',)

    def __str__(self):
        return 'Tag "{0}"'.format(self.name)


class OrderConfirmationDocument(models.Model):
    document = models.FileField(upload_to=get_upload_path)
    name = models.CharField(max_length=300)
    order = models.ForeignKey('tasks.Order', related_name='order_confirmation_documents', on_delete=models.CASCADE)
    tags = models.ManyToManyField('Tag', related_name='order_confirmation_documents', blank=True)
