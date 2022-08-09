from django.db import models
from django.utils import timezone

from django_fsm import FSMField, transition
from jsonfield import JSONField
from model_utils.models import TimeStampedModel

from ..serializers.fields import UTCTimestampField


class DelayedTaskBase(TimeStampedModel, models.Model):
    FAILED = 'failed'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    CREATED = 'created'

    WARNING = 'WARN'
    ERROR = 'ERR'
    INFO = 'INFO'
    PROGRESS = 'PROGRESS'

    _serializer = UTCTimestampField(precision=UTCTimestampField.MS)

    status = FSMField(default=CREATED)
    log = JSONField(default=[])

    def is_in(self, status):
        return self.status == status

    @transition(field=status, source=CREATED, target=IN_PROGRESS)
    def begin(self, *args, **kwargs):
        self._when_begin(*args, **kwargs)

    def _when_begin(self, *args, **kwargs):
        raise NotImplementedError()

    @transition(field=status, source='*', target=FAILED)
    def fail(self, *args, **kwargs):
        self._when_fail(*args, **kwargs)

    def _when_fail(self, *args, **kwargs):
        raise NotImplementedError()

    @transition(field=status, source=IN_PROGRESS, target=COMPLETED)
    def complete(self, *args, **kwargs):
        self._when_complete(*args, **kwargs)

    def _when_complete(self, *args, **kwargs):
        raise NotImplementedError()

    class Meta:
        abstract = True
        ordering = ('-id', )

    def event(self, message, level, prevent_save=False, additional_details=None):
        if not self.log:
            self.log = []
        self.log.append({
            'level': level,
            'happened_at': self._serializer.to_representation(timezone.now()),
            'message': message,
            **(additional_details or {}),
        })
        if not prevent_save:
            self.save(update_fields=('log',))

    def __str__(self):
        return u'Delayed task base {0}'.format(self.id)


class ModelPrototype(TimeStampedModel):
    content = JSONField()

    class Meta:
        abstract = True
