from __future__ import division

from django.forms.models import model_to_dict


class TrackModelChangesMixin(object):
    trackable_fields = ()

    def __init__(self, *args, **kwargs):
        super(TrackModelChangesMixin, self).__init__(*args, **kwargs)
        self.__initial_tracked_data = self._trackable_data

    @property
    def diff(self):
        return {k: (v, self._trackable_data[k]) for k, v in self.__initial_tracked_data.items()
                if v != self._trackable_data[k]}

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return list(self.diff.keys())

    def save(self, *args, **kwargs):
        """
        Saves model and set initial state.
        """
        super(TrackModelChangesMixin, self).save(*args, **kwargs)
        self.__initial_tracked_data = self._trackable_data

    @property
    def _trackable_data(self):
        return model_to_dict(self, fields=self.trackable_fields)
