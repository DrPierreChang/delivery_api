from django.db.models import Case, CharField, IntegerField, Value, When

from driver.utils import DEFAULT_DRIVER_STATUS, DRIVER_STATUSES_ORDERING_MAP_REVERSED, DRIVER_STATUSES_PARAMS
from tasks.models import Order

QUERY_ANNOTATION = Case(
    *(
        When(
            id__in=Order.all_objects.filter(**item['order_attributes']).values('driver_id'),
            then=Value(item['status'])
        )
        for item in DRIVER_STATUSES_PARAMS
    ),
    default=Value(DEFAULT_DRIVER_STATUS),
    output_field=CharField(),
)

SORT_ANNOTATION = Case(
    *(
        When(
            id__in=Order.all_objects.filter(**item['order_attributes']).values('driver_id'),
            then=Value(DRIVER_STATUSES_ORDERING_MAP_REVERSED[item['status']])
        )
        for item in DRIVER_STATUSES_PARAMS
    ),
    default=Value(DRIVER_STATUSES_ORDERING_MAP_REVERSED[DEFAULT_DRIVER_STATUS]),
    output_field=IntegerField(),
)
