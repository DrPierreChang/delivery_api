from collections import OrderedDict

from django.utils import timezone

from rest_framework.exceptions import ValidationError

from crequest.middleware import CrequestMiddleware


class TimeMismatchingError(ValidationError):
    message = 'Time mismatching.'
    code = 'time_mismatching'

    def __init__(self, reason, **kwargs):
        self.detail = OrderedDict(
            [
                ('message', self.message),
                ('server_time', timezone.now()),
                ('reason', reason),
                ('code', self.code)
            ] + list(kwargs.items())
        )
        if CrequestMiddleware.get_request().version >= 2:
            self.detail = [self.detail]
        super(TimeMismatchingError, self).__init__(self.detail, code=self.code)


__all__ = ['TimeMismatchingError']
