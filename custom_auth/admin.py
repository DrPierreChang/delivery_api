from __future__ import absolute_import

from django.contrib import admin

from drf_secure_token.admin import TokenAdmin
from drf_secure_token.models import Token

from radaro_utils.radaro_admin.admin import Select2FiltersMixin


class CustomTokenAdmin(Select2FiltersMixin, TokenAdmin):
    list_display = ('key', 'user', 'get_user_merchant', 'created', 'expire_in', 'dead_in', 'marked_for_delete', )
    list_filter = ('user', 'user__merchant', )
    search_fields = ('key', 'user__merchant__name', 'user__first_name',
                     'user__last_name', 'user__email', 'user__phone', )

    raw_id_fields = ('user', )
    autocomplete_lookup_fields = {
        'fk': ['user', ],
    }

    def get_user_merchant(self, obj):
        return obj.user.current_merchant

    get_user_merchant.short_description = 'Merchant'
    get_user_merchant.admin_order_field = 'user__merchant__name'

admin.site.unregister(Token)
admin.site.register(Token, CustomTokenAdmin)
