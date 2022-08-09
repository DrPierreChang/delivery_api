from __future__ import absolute_import, unicode_literals

from django.contrib import admin
from django.contrib.admin.actions import delete_selected
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from radaro_utils.filters.date_filters import RadaroDateTimeRangeFilter
from radaro_utils.radaro_admin.admin import Select2FiltersMixin
from reporting.context_managers import track_fields_on_change
from reporting.model_mapping import serializer_map
from reporting.utils.delete import create_delete_event

from .models import Event, ExportReportInstance
from .signals import send_create_event_signal


class TrackableModelAdmin(admin.ModelAdmin):
    excluded_fields_from_tracking = None

    def response_add(self, request, obj, post_url_continue=None):
        self._created_object = obj
        return super().response_add(request, obj, post_url_continue)

    def update_object(self, request, object_id, form_url, extra_context):
        instance = self.get_object(request, object_id)
        with track_fields_on_change(instance, initiator=request.user, sender=self):
            result = super().changeform_view(request, object_id, form_url, extra_context)
        return result

    def create_object(self, request, object_id, form_url, extra_context):
        result = super().changeform_view(request, object_id, form_url, extra_context)
        if hasattr(self, '_created_object'):
            instance = self._created_object

            DeltaSerializer = serializer_map.get_for(self.model)
            dump = DeltaSerializer(instance).data
            dump.update({
                'str_repr': str(instance),
                'content_type': ContentType.objects.get_for_model(
                    model=self.model, for_concrete_model=False
                ).model.title()
            })
            event = Event.generate_event(
                self, initiator=request.user, object=instance, obj_dump=dump, event=Event.CREATED,
            )
            send_create_event_signal(events=[event])

        return result

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST':
            if object_id:
                return self.update_object(request, object_id, form_url, extra_context)
            else:
                return self.create_object(request, object_id, form_url, extra_context)

        return super().changeform_view(request, object_id, form_url, extra_context)

    @transaction.atomic
    def delete_model(self, request, obj):
        create_delete_event(self, obj, request.user, request)
        return super(TrackableModelAdmin, self).delete_model(request, obj)


class EventModelAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('happened_at', 'created_at', 'object_name', 'field', 'new_value', 'initiator', 'event', 'merchant')
    list_prefetch_related = ('object', 'initiator', 'content_type', 'merchant',)
    list_filter = ('field', 'initiator', 'event', 'merchant',
                   ('happened_at', RadaroDateTimeRangeFilter), ('created_at', RadaroDateTimeRangeFilter))
    search_fields = ('new_value',)

    raw_id_fields = ('initiator', 'merchant', 'content_type',)
    autocomplete_lookup_fields = {
        'fk': ['initiator', 'merchant', ],
    }

    def get_queryset(self, request):
        qs = super(EventModelAdmin, self).get_queryset(request)
        return qs.prefetch_related(*self.list_prefetch_related)


class ExportReportInstanceAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('id', 'created', 'merchant', 'status')
    list_filter = ('created', 'merchant', 'status')
    list_select_related = ('merchant', )

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ]
    }


# To track multiple deletion of objects from admin we use small hacks:
# 1) We disable original delete_selected and set custom trackable_deletion_objects()
# 2) This method tracks modeladmin instance if it is subclass of TrackableModelAdmin:
#    if it's not - we run original method without changes, otherwise we change coming queryset's delete()
#    on custom which send event on every object's deletion, after that we call original delete method and
#    set it back as delete().

# Fabric that returns trackable deletion method, initialized with queryset
def trackable_deletion(q, initiator):
    def inner_delete():
        self = q
        for obj in self.all():
            create_delete_event(self, obj, initiator)
        self.delete_query()
        self.delete = self.delete_query

    return inner_delete


# Custom method instead of original delete_selected
# Track modeladmin instance if it is subclass of TrackableModelAdmin and change delete()
def trackable_deletion_objects(modeladmin, request, queryset):

    if issubclass(modeladmin.__class__, TrackableModelAdmin):
        queryset.delete_query = queryset.delete
        initiator = request.user
        queryset.delete = trackable_deletion(queryset, initiator)
    return delete_selected(modeladmin, request, queryset)

trackable_deletion_objects.short_description = "Delete selected %(verbose_name_plural)s"

admin.site.register(Event, EventModelAdmin)
admin.site.register(ExportReportInstance, ExportReportInstanceAdmin)

admin.site.disable_action('delete_selected')
admin.site.add_action(trackable_deletion_objects, 'delete_selected')
