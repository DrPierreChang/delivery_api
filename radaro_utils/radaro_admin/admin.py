from django.conf import settings
from django.templatetags.static import static

from constance import config


class Select2FiltersMixin(object):
    class Media:
        js = (
            static('js/admin_filters_select2/jquery.init.js'),
            'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/js/select2.min.js',
            static('js/admin_filters_select2/admin_filters_select2.js'),
        )
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/css/select2.min.css',)
        }


class RemoveDeleteActionMixin(object):
    def get_actions(self, request):
        actions = super(RemoveDeleteActionMixin, self).get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class MaxNumInlinesMixin(object):
    def get_max_num(self, request, obj=None, **kwargs):
        if self.max_num is None:
            self.max_num = config.CONFIRM_PHOTOS_UPLOAD_LIMIT
        return super(MaxNumInlinesMixin, self).get_max_num(request, obj, **kwargs)


class SuperuserRequiredMixin(object):
    superuser_fieldsets = None
    superuser_fields = None

    def get_fieldsets(self, request, obj=None):
        if obj and request.user.email in settings.ADMIN_SITE_SUPERADMINS and self.superuser_fieldsets:
            return (self.fieldsets or tuple()) + self.superuser_fieldsets
        return super(SuperuserRequiredMixin, self).get_fieldsets(request, obj)

    def get_fields(self, request, obj=None):
        if obj and request.user.email in settings.ADMIN_SITE_SUPERADMINS and self.superuser_fields:
            return (self.fields or tuple()) + self.superuser_fields
        return super(SuperuserRequiredMixin, self).get_fields(request, obj)
