from rest_framework import serializers

from radaro_utils.helpers import utc_localize_from_timestamp
from route_optimisation.logging import EventLabel, log_item_registry


class LogField(serializers.JSONField):
    def to_representation(self, value, optimisation=None):
        return {
            'messages': self.get_messages(value.log.get('full', []), optimisation),
            'progress': value.log.get('progress'),
            'steps': value.log.get('steps', []),
        }

    def get_messages(self, logs, optimisation):
        result = []
        preceding_valid_items = []
        for log_item in logs:
            if EventLabel.DEV in log_item.get('labels', []):
                continue
            log_class = log_item_registry.get(log_item.get('event'))
            text = log_class and log_class.build_message_for_web(log_item, optimisation, preceding_valid_items)
            if not text:
                continue
            _time = utc_localize_from_timestamp(float(log_item['timestamp']))
            msg = {
                'text': text,
                'time': serializers.DateTimeField().to_representation(_time)
            }
            result.append(msg)
            preceding_valid_items.append(log_item)
        return result
