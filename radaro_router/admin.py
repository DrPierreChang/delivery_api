from django import forms
from django.contrib import admin

from radaro_router.models import RadaroRouter
from radaro_utils.utils import get_content_types_for


class RadaroRouterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        remote_instance_choices = ['base.member', 'base.invite', ]
        super(RadaroRouterForm, self).__init__(*args, **kwargs)
        self.fields['content_type'].queryset = get_content_types_for(remote_instance_choices)


@admin.register(RadaroRouter)
class RadaroRouterAdmin(admin.ModelAdmin):
    form = RadaroRouterForm

    list_display = ('id', 'object', 'content_type', 'last_action', 'created_at', 'synced')
    list_filter = ('synced', )
