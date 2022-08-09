from django.contrib import admin


class BaseRelatedOnlyFieldListFilter(admin.SimpleListFilter):
    qs = []

    def lookups(self, request, model_admin):
        return [(related_obj.id, related_obj) for related_obj in self.qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{'%s__exact' % self.parameter_name: self.value()})
        else:
            return queryset
