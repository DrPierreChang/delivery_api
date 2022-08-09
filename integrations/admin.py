from django.contrib import admin

from .models import RevelSystem


@admin.register(RevelSystem)
class RevelSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'subdomain', 'merchant', )
    list_select_related = ('merchant', )

    exclude = ('importing', )
