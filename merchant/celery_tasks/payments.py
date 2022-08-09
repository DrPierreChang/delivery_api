import sentry_sdk
from celery.schedules import crontab
from celery.task import periodic_task
from pinax.stripe.actions import charges
from pinax.stripe.actions.customers import can_charge

from base.models import Member
from delivery.celery import app
from notification.models import MerchantMessageTemplate

from ..models import Merchant


@app.task()
def merchant_charge(merchant_id):
    merchant = Merchant.objects.filter(id=merchant_id).first()
    admin = merchant.member_set.filter(role=Member.ADMIN).first()
    amount = abs(merchant.balance)
    if not admin:
        return
    if hasattr(admin, 'customer') and can_charge(admin.customer):
        try:
            charges.create(
                amount=amount,
                customer=admin.customer.stripe_id,
                currency="aud",
                description="Automatic charge"
            )
            merchant.change_balance(amount)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
    else:
        admin.send_notification(send_sms=False, template_type=MerchantMessageTemplate.BILLING,
                                merchant_id=merchant.id)


@periodic_task(run_every=crontab(0, 10, day_of_month='1'))
def every_month_billing():
    for merchant in Merchant.objects.filter(balance__lt=0):
        merchant_charge.delay(merchant.id)


@periodic_task(run_every=crontab(0, 10, day_of_month='4'))
def check_payment():
    queryset = Merchant.objects.filter(balance__lt=0)
    merchants = list(queryset)
    queryset.update(is_blocked=True)
    for merchant in merchants:
        admin = merchant.member_set.filter(role=Member.ADMIN).first()
        if not admin:
            return
        admin.send_notification(send_sms=False, template_type=MerchantMessageTemplate.ACCOUNT_LOCKED,
                                merchant_id=merchant.id)


__all__ = ['merchant_charge', 'every_month_billing', 'check_payment', ]
