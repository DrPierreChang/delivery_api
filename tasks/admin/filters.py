from django.contrib import admin


class ExternalJobFilter(admin.SimpleListFilter):
    title = 'Is external job'
    parameter_name = 'external_job'

    YES = 'yes'
    NO = 'no'

    def lookups(self, request, model_admin):
        return (
            (self.YES, 'Yes'),
            (self.NO, 'No'),
        )

    def queryset(self, request, queryset):
        if self.value():
            kw = {}
            if self.value() == self.YES:
                kw['external_job__isnull'] = False
            elif self.value() == self.NO:
                kw['external_job__isnull'] = True
            return queryset.filter(**kw)
