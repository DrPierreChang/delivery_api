from distutils.util import strtobool

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case, Prefetch, When
from django.db.models.functions import Cast

from radaro_utils.files.utils import get_upload_path
from radaro_utils.models import ResizeImageMixin


def get_checklist_default_invite_text():
    return '<div class="preSurveyModal__title"></div>\n<div class="preSurveyModal__message"></div>'


class Checklist(models.Model):
    JOB = 1
    START_OF_DAY = 2
    SURVEY = 3
    END_OF_DAY = 4

    type_choices = (
        (JOB, 'Job Checklist'),
        (START_OF_DAY, 'Start of Day Checklist'),
        (SURVEY, 'Survey'),
        (END_OF_DAY, 'End of Day Checklist'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    checklist_type = models.PositiveSmallIntegerField(choices=type_choices, default=JOB, db_index=True)
    invite_text = models.TextField(blank=True, default=get_checklist_default_invite_text)
    thanks_text = models.TextField(blank=True, default=get_checklist_default_invite_text)

    def __str__(self):
        name_map = dict(self.type_choices)
        return "{0} {1}".format(name_map[self.checklist_type], self.title)

    @property
    def questions(self):
        prf_question_answers = Prefetch(
            'answers',
            queryset=Answer.objects.filter(question__category=Question.DICHOTOMOUS, is_correct=True),
            to_attr='correct_answers'
        )
        return Question.objects.filter(section__checklist_id=self.id).prefetch_related(prf_question_answers)

    @property
    def questions_text(self):
        return self.questions.values_list('text', flat=True)


class Section(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    checklist = models.ForeignKey(Checklist, related_name='sections', on_delete=models.CASCADE)
    consecutive_number = models.IntegerField(null=True, validators=[MinValueValidator(1)])

    def __str__(self):
        return 'Section "{0}"'.format(self.title)


class Question(ResizeImageMixin, models.Model):
    DICHOTOMOUS = 'dichotomous'
    MULTIPLE_CHOICE = 'multiple_choice'
    SINGLE_CHOICE = 'single_choice'
    TEXT = 'text'
    SCALE = 'scale'

    question_categories = (
        (DICHOTOMOUS, 'Dichotomous'),
        (MULTIPLE_CHOICE, 'Multiple Choice (Multi-Selection)'),
        (SINGLE_CHOICE, 'Multiple Choice (Single-Selection)'),
        (TEXT, 'Text Response'),
        (SCALE, 'NPS & Scale Slider')
    )

    _checklist_categories_num = 1
    checklist_question_categories = question_categories[:_checklist_categories_num]
    survey_question_categories = question_categories[_checklist_categories_num:]

    text = models.TextField()
    description = models.TextField(null=True, blank=True)
    section = models.ForeignKey(Section, related_name='questions', on_delete=models.CASCADE)
    category = models.CharField(choices=question_categories, default=DICHOTOMOUS, max_length=50)
    description_image = models.ImageField(upload_to=get_upload_path, null=True, blank=True)
    consecutive_number = models.IntegerField(null=True, validators=[MinValueValidator(1)])
    subtitles = ArrayField(models.CharField(max_length=100), default=list, blank=True)

    class Meta:
        ordering = ('section', 'consecutive_number')

    def __str__(self):
        return "Question: {0}".format(self.text)

    @staticmethod
    def autocomplete_search_fields():
        return "text__icontains", "id__iexact"

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.description_image and (self.description_image.height > 500 or self.description_image.width > 500):
            self.resize_image(self.description_image)
        if not self.consecutive_number:
            last_question = self.section.questions.last()
            self.consecutive_number = last_question.consecutive_number + 1 if last_question else 1
        super(Question, self).save(force_insert, force_update, using, update_fields)

    @property
    def correct_answer(self):
        if not self.correct_answers:
            return
        correct_answer = self.correct_answers[0]

        return correct_answer.text_as_bool

    @property
    def category_display(self):
        return self.get_category_display()


class AnswerManager(models.Manager):

    def get_queryset(self):
        return super(AnswerManager, self).get_queryset().select_related('question').annotate(
            text_as_bool=Case(
                When(
                    question__category=Question.DICHOTOMOUS,
                    then=Cast('text', models.BooleanField())),
                default=True, output_field=models.BooleanField())
        )


class Answer(models.Model):
    question = models.ForeignKey(Question, related_name='answers', on_delete=models.CASCADE)
    text = models.TextField(blank=True)
    photos_required = models.BooleanField(default=False, verbose_name='Photos must be attached')
    is_correct = models.BooleanField(default=False)
    is_checkbox = models.BooleanField(default=False)

    objects = AnswerManager()

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Question Answer "{0}"'.format(self.text, self.question_id)

    @property
    def choice(self):
        return bool(strtobool(self.text))
