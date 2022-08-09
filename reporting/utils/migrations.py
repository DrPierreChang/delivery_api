import json

from reporting.models import Event


class ModelFieldsEventMigrator(object):
    def __init__(self, apps, content_type, source, destination):
        self.content_type = content_type
        self._from = source
        self._to = destination
        self._events = Event.objects.filter(content_type_id=self.content_type.id)

    def migrate(self):
        events_kwargs = {_dir: dict(zip(('field', 'new_value'), getattr(self, _dir)['values'][0]))
                         for _dir in ('_from', '_to')}
        self._events.filter(event=Event.CHANGED, **events_kwargs['_from']).update(**events_kwargs['_to'])

        _val = '{}:{}'.format(*map(json.dumps, self._from['values'][0]))
        for ev in self._events.filter(event=Event.MODEL_CHANGED, obj_dump__icontains=_val):
            for _field, _ in self._from['values']:
                try:
                    del ev.obj_dump['old_values'][_field]
                    del ev.obj_dump['new_values'][_field]
                except KeyError:
                    pass
            for _field, _value in self._to['values']:
                try:
                    ev.obj_dump['old_values'][_field] = self._to['defaults'][_field]
                    ev.obj_dump['new_values'][_field] = _value
                except KeyError:
                    pass
            ev.save()
