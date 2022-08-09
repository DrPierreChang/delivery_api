from django.contrib import admin

from ..models import Schedule
from .forms import CreateScheduleForm, ScheduleForm


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    form = ScheduleForm
    add_form = CreateScheduleForm
    change_form_template = 'admin/schedule/schedule/change_form.html'

    list_display = ('id', 'member_id', 'member', 'get_merchant')
    list_filter = ('member__merchant',)
    search_fields = ('id', 'member__id', 'member__first_name', 'member__last_name', 'member__username', 'member__email')

    raw_id_fields = ('member',)
    autocomplete_lookup_fields = {
        'fk': ['member'],
    }

    def get_form(self, request, obj=None, **kwargs):
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_merchant(self, schedule):
        return schedule.member.merchant
    get_merchant.short_description = 'Merchant'
