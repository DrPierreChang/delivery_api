from django.contrib import messages

from reporting.context_managers import track_fields_on_change


def deactivate_selected_members(modeladmin, request, queryset):
    for member in queryset:
        with track_fields_on_change(member, initiator=request.user):
            member.is_active = False
            member.save(update_fields=('is_active', ))
    modeladmin.message_user(request,
                            "Successfully deactivated %(count)s members." % {'count': queryset.count()},
                            messages.SUCCESS)
    return None
deactivate_selected_members.short_description = "Deactivate selected members"


def activate_selected_members(modeladmin, request, queryset):
    n = queryset.update(is_active=True)
    modeladmin.message_user(request, "Successfully activated %(count)s members." % {'count': n}, messages.SUCCESS)
    return None
activate_selected_members.short_description = "Activate selected members"
