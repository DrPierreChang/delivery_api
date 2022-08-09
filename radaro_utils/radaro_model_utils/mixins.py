from django.db import models


class TrackMixin(models.Model):
    track_fields = None
    tracker = None

    def __getstate__(self):
        return self.__dict__

    # Remove save and _tracker from __dict__ as they're not serializable by pickle
    # State changes let's save in _tracker_saved_data field
    def __reduce__(self):
        reduce_args = super(TrackMixin, self).__reduce__()
        _dict = reduce_args[2].copy()
        _dict['_tracker_saved_data'] = _dict.pop('_tracker').saved_data
        return reduce_args[0], reduce_args[1], _dict

    # Restore basic save and re-initialize tracker field, that basically initialized on post_init
    def __setstate__(self, state):
        Model = type(self)
        state['save'] = Model.save.__get__(self, Model)
        _saved_data = state.pop('_tracker_saved_data')
        super(TrackMixin, self).__setstate__(state)
        Model.tracker.initialize_tracker(Model, self)
        self._tracker.saved_data = _saved_data

    def should_notify(self):
        return set()

    def save(self, update_fields=None, exclude_should_notify=None, *args, **kwargs):
        should_notify = (self.track_fields & set(self.tracker.changed())) | self.should_notify()
        if update_fields:
            should_notify &= set(update_fields)
        if exclude_should_notify:
            should_notify -= set(exclude_should_notify)
        for f_name in should_notify:
            pre_save_hook = getattr(self, '_on_{}_change'.format(f_name))
            pre_save_hook(previous=self.tracker.previous(f_name))
        super(TrackMixin, self).save(update_fields=update_fields, *args, **kwargs)

    class Meta:
        abstract = True
