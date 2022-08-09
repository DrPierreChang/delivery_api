from __future__ import absolute_import, unicode_literals

from django.contrib import admin
from django.db.models import Case, F, IntegerField, Q, When

from merchant.models.mixins import MerchantTypes

from ..models import MerchantMessageTemplate


class MerchantTemplateInlineAdmin(admin.TabularInline):
    model = MerchantMessageTemplate
    extra = 1
    can_delete = False
    fields = ('text', 'html_text', 'subject', 'template_type', 'enabled')
    readonly_fields = ('template_type', )

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super(MerchantTemplateInlineAdmin, self).get_queryset(request)
        return queryset.filter(Q(template_type__in=MerchantMessageTemplate.merchant_customizable_templates)
                               | Q(template_type=MerchantMessageTemplate.SPECIAL_MIELE_SURVEY,
                                   merchant__merchant_type=MerchantTypes.MERCHANT_TYPES.MIELE_SURVEY))\
            .annotate(
            sort_rate=Case(
                When(template_type=MerchantMessageTemplate.UPCOMING_DELIVERY, then=-2),
                When(template_type=MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY, then=-1),
                default=F('id'), output_field=IntegerField()
            )
        ).order_by('sort_rate')
