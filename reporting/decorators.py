from functools import wraps

from rest_framework.permissions import SAFE_METHODS

from .api.legacy.serializers import serializers
from .context_managers import track_fields_for_offline_changes


# TODO: tracking creating/deleting
# Use only in subclasses of GenericView as its methods are used.
# Ready for updating only.
def log_fields_on_object(fields=None, ignore_methods=None):
    _ignorable = ignore_methods if ignore_methods else ()

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            self = args[0]
            if self.request.method not in _ignorable + SAFE_METHODS:
                offline_serializer = serializers.OfflineHappenedAtSerializer(data={
                    'offline_happened_at': self.request.data.get('offline_happened_at')
                })
                if offline_serializer.is_valid():
                    offline_happened_at = offline_serializer.validated_data.get('offline_happened_at')
                else:
                    offline_happened_at = None
                kwargs['offline_happened_at'] = offline_happened_at

                with track_fields_for_offline_changes(self.get_object(), self, self.request, offline_happened_at):
                    response = view(*args, **kwargs)

                return response
            return view(*args, **kwargs)
        return wrapper
    return decorator
