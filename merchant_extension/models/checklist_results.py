from datetime import timedelta

from django.db import models
from django.utils import timezone

from model_utils import FieldTracker

from base.models import Member
from merchant.image_specs import ThumbnailGenerator
from radaro_utils.db import LockedAtomicTransaction, LockMode
from radaro_utils.files.utils import get_upload_path
from radaro_utils.models import AttachedPhotoBase
from radaro_utils.radaro_model_utils.mixins import TrackMixin

from ..celery_tasks import handle_wrong_answers_eod_checklist, handle_wrong_answers_sod_checklist
from .base import Checklist


class ResultChecklistQuerySet(models.QuerySet):
    def get_current_sod_checklist(self, driver):
        with LockedAtomicTransaction(ResultChecklist, lock_mode=LockMode.EXCLUSIVE):
            try:
                qs = self.filter_today_checklists(driver.current_merchant.timezone)
                qs = qs.filter(checklist__checklist_type=Checklist.START_OF_DAY)
                instance = qs.get(driver=driver)
            except ResultChecklist.DoesNotExist:
                instance = self.create(driver=driver, checklist=driver.current_merchant.sod_checklist)
            return instance

    def get_current_eod_checklist(self, driver):
        with LockedAtomicTransaction(ResultChecklist, lock_mode=LockMode.EXCLUSIVE):
            try:
                qs = self.filter_today_checklists(driver.current_merchant.timezone)
                qs = qs.filter(checklist__checklist_type=Checklist.END_OF_DAY)
                instance = qs.get(driver=driver)
            except ResultChecklist.DoesNotExist:
                instance = self.create(driver=driver, checklist=driver.current_merchant.eod_checklist)
            return instance

    def filter_today_checklists(self, merchant_tz):
        today_start = timezone.now().astimezone(merchant_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        today_range = (today_start, today_start + timedelta(days=1))
        return self.filter(created_at__range=today_range)


class ResultChecklist(models.Model):
    checklist = models.ForeignKey(Checklist, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    date_of_risk_assessment = models.DateTimeField(null=True, blank=True, auto_now=True)
    confirmation_signature = models.ImageField(null=True, blank=True, upload_to=get_upload_path)
    confirmation_comment = models.TextField(null=True, blank=True)
    is_correct = models.NullBooleanField()
    driver = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL)

    objects = ResultChecklistQuerySet.as_manager()

    class Meta:
        verbose_name = 'Checklist Result'
        verbose_name_plural = 'Checklist Results'

    def __str__(self):
        return "Result checklist with id: {0}".format(self.id)

    @staticmethod
    def autocomplete_search_fields():
        return "confirmation_comment__icontains", "id__iexact"

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        has_wrong_answers = False
        if self.is_correct is None and self.result_answers.exists():
            self.is_correct = self.checklist_is_correct()
            has_wrong_answers = not self.is_correct
        super(ResultChecklist, self).save(force_insert, force_update, using, update_fields)
        if has_wrong_answers:
            if self.checklist.checklist_type == Checklist.START_OF_DAY:
                handle_wrong_answers_sod_checklist.delay(self.id)
            if self.checklist.checklist_type == Checklist.END_OF_DAY:
                handle_wrong_answers_eod_checklist.delay(self.id)

    @property
    def checklist_merchant(self):
        if self.driver:
            return self.driver.current_merchant
        elif hasattr(self, 'order') and self.order:
            return self.order.merchant

    def get_answers(self):
        return self.result_answers.annotate_correct_answer().order_by('answer__question__consecutive_number') \
            .values_list('correct_answer', flat=True)

    def checklist_is_correct(self):
        answers = self.get_answers()

        if hasattr(self, 'order') and self.order and self.order.merchant.is_nti:
            return answers.last()
        return all(answers)

    @property
    def title(self):
        return self.checklist.title

    @property
    def is_passed(self):
        return self.is_correct is not None

    @property
    def is_confirmed(self):
        if not hasattr(self, 'order'):
            return False

        # TODO: remove confirmation from result checklist
        pre_confirmation = bool(self.order.pre_confirmation_comment or self.order.pre_confirmation_signature
                                or self.order.pre_confirmation_photos.exists())
        checklist_confirmation = bool(self.confirmation_comment or self.confirmation_signature
                                      or self.confirmation_photos.exists())

        return pre_confirmation or checklist_confirmation


class SurveyResultManager(models.Manager):

    def get_queryset(self):
        return super(SurveyResultManager, self).get_queryset() \
            .filter(checklist__checklist_type=Checklist.SURVEY)


class SurveyResult(ResultChecklist):
    objects = SurveyResultManager()

    class Meta:
        proxy = True
        verbose_name = 'Survey Result'
        verbose_name_plural = 'Survey Results'

    @property
    def is_passed(self):
        return self.result_answers.exists()


class ResultChecklistConfirmationPhoto(TrackMixin, AttachedPhotoBase):
    thumbnailer = ThumbnailGenerator({'image': 'thumb_image_100x100_field'})
    tracker = FieldTracker()
    track_fields = {'image'}

    result_checklist = models.ForeignKey(ResultChecklist, related_name='confirmation_photos', on_delete=models.CASCADE)
