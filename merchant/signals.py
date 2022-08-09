from django.db.models.signals import post_save
from django.dispatch import receiver

from tasks.models import Order

from .models import Merchant


@receiver(post_save, sender=Order)
def decrease_merchant_balance(sender, instance, created, *args, **kwargs):
    if created:
        m = Merchant.objects.get(id=instance.merchant_id)
        amount = -instance.cost
        m.change_balance(amount=amount)
