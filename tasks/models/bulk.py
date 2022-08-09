from __future__ import absolute_import, unicode_literals

from collections import namedtuple

from django.db import models
from django.db.models import Case, Count, Q, Sum, When
from django.utils import timezone

from bulk_update.helper import bulk_update
from django_fsm import transition
from jsonfield import JSONField

from merchant.models import Merchant
from radaro_utils.radaro_csv.exceptions import CSVEncodingError
from radaro_utils.radaro_csv.models import CSVFile
from radaro_utils.radaro_delayed_tasks.models import DelayedTaskBase, ModelPrototype
from reporting.models import Event
from tasks.models.external import ExternalJob

from .bulk_serializer_mapping import prototype_serializers

FakeRequest = namedtuple('FakeRequest', 'user GET')


class BulkDelayedUpload(DelayedTaskBase):
    CONFIRMED = 'confirmed'
    READY = 'ready'

    WEB = 'web'
    API = 'api'
    NO_INFO = 'no_info'
    EXTERNAL_API = 'external'

    allowed_serializer_names = (
        (name, name.upper()) for name in prototype_serializers.allowed_names
    )

    _method = (
        (WEB, 'WEB'),
        (API, 'API'),
        (EXTERNAL_API, 'External API'),
        (NO_INFO, 'No info')
    )

    merchant = models.ForeignKey(Merchant, null=True, on_delete=models.SET_NULL)
    unpack_serializer = models.CharField(max_length=256, editable=False, choices=allowed_serializer_names,
                                         default=prototype_serializers.CSV)

    creator = models.ForeignKey('base.Member', null=True, blank=True, on_delete=models.SET_NULL)
    method = models.CharField(choices=_method, default=NO_INFO, max_length=10)
    uploaded_from = models.CharField(max_length=512, blank=True)

    def get_serializer_class(self):
        return prototype_serializers.get(self.unpack_serializer)

    def update_state(self):
        if not hasattr(self, '_stats'):
            self._stats = self.prototypes.aggregate(
                successful=Sum(Case(When(errors='', then=1), output_field=models.IntegerField(), default=0)),
                processed=Count('id'),
                saved=Count('order__id'),
            )
            self._stats.update({
                'errors_found': self._stats['processed'] - (self._stats['successful'] or 0),
            })

    def _finish(self, *args, **kwargs):
        self.prototypes.filter(ready=True).update(processed=True, ready=False)

    def _when_begin(self, *args, **kwargs):
        pass

    def is_possible(self, raise_exception=True):
        if self.is_in(BulkDelayedUpload.FAILED) or self.is_in(BulkDelayedUpload.CONFIRMED):
            if raise_exception:
                raise Exception('Bulk uploading has been failed or confirmed before.')
            return False
        return True

    def check_errors_and_next_state(self):
        self.update_state()
        if self._stats['errors_found'] or not self._stats['successful']:
            self.fail()
        else:
            self.ready()

    @transition(field='status', source=DelayedTaskBase.IN_PROGRESS, target=READY)
    def ready(self):
        pass

    @transition(field='status', source=READY, target=DelayedTaskBase.IN_PROGRESS)
    def continues(self):
        pass

    def _when_complete(self, *args, **kwargs):
        pass

    def _when_confirm(self, *args, **kwargs):
        self._finish(*args, **kwargs)

    def _when_fail(self, *args, **kwargs):
        self._finish(*args, **kwargs)

    @transition(field='status', source=DelayedTaskBase.COMPLETED, target=CONFIRMED)
    def confirm(self, *args, **kwargs):
        self._when_confirm(*args, **kwargs)

    def event(self, message, level, force_save=False):
        super(BulkDelayedUpload, self).event(message, level, True)
        if force_save or not self.last:
            self.last = timezone.now()
            self.save()
        else:
            tz = timezone.now()
            if (tz - self.last).total_seconds() > 1:
                self.last = tz
                self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self.id:
            self.event('File processing started.', BulkDelayedUpload.INFO)
        super(DelayedTaskBase, self).save(force_insert, force_update, using, update_fields)

    @property
    def errors(self):
        return self.prototypes.exclude(Q(errors='') | Q(errors__isnull=True)).order_by('line')

    @property
    def state_params(self):
        self.update_state()
        return dict(self._stats, **{
            'lines': self.csv_file.lines,
            'encoding': self.csv_file.encoding
        })

    def create_orders(self, *slice_indexes):
        fake_request = FakeRequest(user=self.creator, GET={})
        SerializerClass = self.get_serializer_class()
        prototypes = self.prototypes.filter(errors='', processed=False)[slice(*slice_indexes)]
        serializer = SerializerClass(
            data=prototypes,
            context={'request': fake_request, 'merchant': self.merchant}
        )
        serializer.is_valid(raise_exception=True)
        orders = serializer.create_orders(
            manager=self.creator,
            bulk=self
        )
        bulk_update(prototypes, update_fields=['ready', 'errors'])
        return orders

    def __init__(self, *args, **kwargs):
        super(BulkDelayedUpload, self).__init__(*args, **kwargs)
        self.last = timezone.now()

    @staticmethod
    def autocomplete_search_fields():
        return 'id__iexact', 'status__icontains', 'method__icontains', 'merchant__name__icontains'


class OrderPrototypeQuerySet(models.QuerySet):
    def create_orders(self, initiator):
        events = []
        fake_request = FakeRequest(user=initiator, GET={})
        for o_p in self:
            serializer = o_p.get_serializer()(data=o_p.content, context={'request': fake_request})
            if serializer.is_valid():
                save_kwargs = {
                    'bulk_id': o_p.bulk_id,
                    'model_prototype': o_p,
                    'manager': initiator,
                    'merchant_id': initiator.current_merchant_id
                }
                if o_p.external_job_id:
                    save_kwargs['external_job_id'] = o_p.external_job_id
                order = serializer.save(**save_kwargs)
                events.append(Event(object=order, obj_dump=order.order_dump, initiator=initiator,
                                    merchant_id=initiator.current_merchant_id, event=Event.CREATED))
            else:
                o_p.errors = serializer.errors
            o_p.mark_as_ready(save=False)
        bulk_update(self, update_fields=['ready', 'errors'])
        return Event.objects.bulk_create(events)


class OrderPrototypeManager(models.Manager):
    def get_queryset(self):
        return OrderPrototypeQuerySet(self.model, using=self._db)


class OrderPrototype(ModelPrototype):
    external_job = models.OneToOneField(
        ExternalJob, null=True, blank=True,
        related_name='order_prototype', on_delete=models.CASCADE
    )
    processed = models.BooleanField(default=False)
    bulk = models.ForeignKey(BulkDelayedUpload, related_name='prototypes', on_delete=models.CASCADE)
    ready = models.BooleanField(default=False)
    errors = JSONField(blank=True)
    line = models.PositiveIntegerField(default=0)

    objects = OrderPrototypeManager()

    def mark_as_ready(self, save=True):
        self.ready = True
        if save:
            self.save(update_fields=('ready',))

    def __str__(self):
        return 'From bulk: {}'.format(self.bulk_id)

    class Meta:
        ordering = ('id',)


class CSVOrdersFile(CSVFile):
    bulk = models.OneToOneField(BulkDelayedUpload, related_name='csv_file', on_delete=models.CASCADE)

    def _on_create(self):
        from ..csv_parsing import _messages

        try:
            super(CSVOrdersFile, self)._on_create()
        except CSVEncodingError as err:
            self.bulk.fail()
            self.bulk.event(str(err), BulkDelayedUpload.ERROR, force_save=True)
        except Exception:
            self.bulk.fail()
            self.bulk.event(_messages['critical'], BulkDelayedUpload.ERROR, force_save=True)
        finally:
            self.original_file_name = self.file.name
