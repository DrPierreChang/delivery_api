import json

from django import forms

from radaro_utils.helpers import utc_localize_from_timestamp
from route_optimisation.logging import log_item_registry


class LogWidget(forms.MultiWidget):
    template_name = 'admin/ro_logs.html'

    def __init__(self, attrs=None):
        widgets = [forms.Textarea(attrs={})]
        super().__init__(widgets=widgets, attrs=attrs)
        self.optimisation = None

    def decompress(self, value):
        self.widgets = [forms.Textarea(attrs={'value': self._prepare_log_item(log_item)})
                        for log_item in value.get('full', [])]
        return [log_item for log_item in value.get('full', [])]

    def _prepare_log_item(self, log_item):
        log_item['time'] = str(utc_localize_from_timestamp(float(log_item['timestamp'])))
        if 'event' in log_item:
            log_class = log_item_registry.get(log_item.get('event'))
            if log_class:
                log_item['msg'] = log_class.build_message(log_item, self.optimisation, [])
        return log_item
