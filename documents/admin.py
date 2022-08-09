from django.contrib import admin

from .models import OrderConfirmationDocument, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_filter = ('merchant',)
    list_display = ('id', 'name', 'merchant')

    list_select_related = ('merchant',)

    search_fields = ('id', 'name')

    raw_id_fields = ('merchant',)
    autocomplete_lookup_fields = {
        'fk': ['merchant'],
    }


@admin.register(OrderConfirmationDocument)
class OrderConfirmationDocumentAdmin(admin.ModelAdmin):
    list_filter = ('tags',)
    list_display = ('id', 'name', 'order')

    search_fields = ('id', 'name', 'order__id', 'order__title')

    raw_id_fields = ('order',)
    autocomplete_lookup_fields = {
        'fk': ['order'],
    }
