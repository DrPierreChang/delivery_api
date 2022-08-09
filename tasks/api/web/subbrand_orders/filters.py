from django.db.models import F

from rest_framework.filters import OrderingFilter


class SubBrandOrderSortingFilter(OrderingFilter):

    @staticmethod
    def prepare_db_fields(fields, descending=False):
        # Sorting with null being the minimum value
        if isinstance(fields, str):
            fields = [fields]
        if descending:
            return [F(field).desc(nulls_last=True) for field in fields]
        else:
            return [F(field).asc(nulls_first=True) for field in fields]

    def get_ordering(self, request, queryset, view):
        raw_ordering = super().get_ordering(request, queryset, view)

        if raw_ordering:
            valid_fields = self.get_valid_fields(queryset, view, {'request': request})
            valid_fields = {alias: field for alias, field in valid_fields}

            ordering = []
            for alias in raw_ordering:
                ordering += self.prepare_db_fields(
                    fields=valid_fields[alias.lstrip('-')],
                    descending=alias[0] == '-',
                )

            return ordering

        return raw_ordering
