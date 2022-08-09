from django.db import models

from radaro_utils.radaro_phone.models import PhoneField
from tasks.models.mixins import OrderSendNotificationMixin


class Customer(OrderSendNotificationMixin, models.Model):
    email = models.EmailField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=150, blank=False)
    phone = PhoneField(null=True, blank=True)
    merchant = models.ForeignKey('merchant.Merchant', null=True, blank=True, on_delete=models.CASCADE)
    last_address = models.ForeignKey('tasks.OrderLocation', blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return u'{0}: {1}'.format(self.name, self.email)

    @staticmethod
    def autocomplete_search_fields():
        return "email__icontains", "name__icontains", "phone__icontains", "id__iexact"


class Pickup(OrderSendNotificationMixin, models.Model):
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(max_length=50, blank=True)
    phone = PhoneField(blank=True)
    merchant = models.ForeignKey('merchant.Merchant', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return '{}: {}'.format(self.name, self.email or self.phone)

    @staticmethod
    def autocomplete_search_fields():
        return "email__icontains", "name__icontains", "phone__icontains", "id__iexact"
