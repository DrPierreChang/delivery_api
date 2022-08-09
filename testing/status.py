from collections import namedtuple

from tasks.mixins.order_status import OrderStatus

status_dict = {x: v for x, v in vars(OrderStatus).items() if x.isupper()}
Status = namedtuple('Status', list(status_dict.keys()))
STATUS = Status(**status_dict)
