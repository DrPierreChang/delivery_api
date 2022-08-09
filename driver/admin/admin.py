from __future__ import absolute_import

from django.contrib import admin

from driver.filters import LocationsMemberOnlyListFilter
from driver.models import DriverLocation
from radaro_utils.radaro_admin.admin import Select2FiltersMixin


@admin.register(DriverLocation)
class DriverLocationAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('location', 'improved_location',  'member', 'accuracy',
                    'speed', 'bearing', 'created_at', 'timestamp', 'google_request_cost', 'in_progress_orders',
                    'google_requests',)
    list_filter = (LocationsMemberOnlyListFilter, 'member__merchant',)
    search_fields = ('member__merchant__name', 'member__first_name',
                     'member__last_name', 'member__email', 'member__phone',)
    readonly_fields = ('created_at', )
    list_per_page = 75
    ordering = ('-created_at', )
