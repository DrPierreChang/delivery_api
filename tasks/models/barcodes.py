from django.db import models

from merchant.models import Merchant
from tasks.mixins.order_status import OrderStatus


class BarcodeQuerySet(models.QuerySet):
    def confirm_scan_before_delivery(self):
        return self.filter(
            models.Q(order__status=OrderStatus.ASSIGNED, order__pickup_address__isnull=True)
            | models.Q(order__status=OrderStatus.PICK_UP, order__pickup_address__isnull=False)
        ).update(scanned_at_the_warehouse=True)

    def confirm_scan_after_delivery(self):
        return self.filter(order__status=OrderStatus.IN_PROGRESS).update(scanned_upon_delivery=True)

    def merchant_active_barcodes(self, merchant):
        return self.filter(order__merchant_id=merchant.id).exclude(
            order__status__in=[OrderStatus.WAY_BACK, OrderStatus.DELIVERED, OrderStatus.FAILED],
        )


class Barcode(models.Model):
    code_data = models.TextField(db_index=True)
    scanned_at_the_warehouse = models.BooleanField(default=False)
    scanned_upon_delivery = models.BooleanField(default=False)
    required = models.BooleanField(default=False)
    comment = models.TextField(blank=True, default='')
    order = models.ForeignKey('tasks.Order', related_name='barcodes', on_delete=models.CASCADE)

    objects = BarcodeQuerySet.as_manager()

    def __str__(self):
        return self.code_data

    @property
    def scanned(self):
        return self.scanned_at_the_warehouse or self.scanned_upon_delivery

    @scanned.setter
    def scanned(self, scanned):
        scanned_field = self.get_scanned_field()
        if scanned_field:
            setattr(self, scanned_field, scanned)

    def get_scanned_field(self):
        if self.order.merchant.option_barcodes == Merchant.TYPES_BARCODES.both:
            if self.order.status in [OrderStatus.ASSIGNED, OrderStatus.PICK_UP]:
                return 'scanned_at_the_warehouse'
            if self.order.status == OrderStatus.IN_PROGRESS:
                return 'scanned_upon_delivery'

        elif self.order.merchant.option_barcodes == Merchant.TYPES_BARCODES.before:
            return 'scanned_at_the_warehouse'

        elif self.order.merchant.option_barcodes == Merchant.TYPES_BARCODES.after:
            return 'scanned_upon_delivery'

        return None
