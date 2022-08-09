from django.contrib import admin
from django.forms import inlineformset_factory, models

from nested_admin.nested import NestedModelAdmin, NestedStackedInline, NestedTabularInline

from merchant_extension.models import (
    Answer,
    Checklist,
    ImageLocation,
    Question,
    ResultChecklist,
    ResultChecklistAnswer,
    ResultChecklistAnswerPhoto,
    ResultChecklistConfirmationPhoto,
    Section,
)
from radaro_utils.radaro_admin.admin import MaxNumInlinesMixin, Select2FiltersMixin

from ..forms import AnswerForm, ChecklistForm
from .utils import filtered_question_category_formset, unique_field_formset


class DichotomousQuestionFormset(models.BaseInlineFormSet):
    def clean(self):
        super(DichotomousQuestionFormset, self).clean()
        if any(self.errors) or not self.instance.category == Question.DICHOTOMOUS:
            return
        forms_num = len(list(filter(lambda form: 'DELETE' not in form.changed_data, self.forms)))
        if forms_num != 2 and self.parent_form:
            self.parent_form.add_error(None, 'Dichotomous question should contain 2 answers!')


class AnswerNestedInline(NestedStackedInline):
    model = Answer
    extra = 0
    formset = inlineformset_factory(
        Question, Answer, formset=DichotomousQuestionFormset, fields='__all__'
    )
    form = AnswerForm


class BaseQuestionNestedInline(NestedStackedInline):
    model = Question
    inlines = [AnswerNestedInline, ]
    extra = 0
    ordering = ('consecutive_number',)


class ChecklistQuestionNestedInline(BaseQuestionNestedInline):
    formset = inlineformset_factory(
        Section, Question,
        formset=filtered_question_category_formset(
            base_class=unique_field_formset(('consecutive_number', 'section_id')),
            question_categories=Question.checklist_question_categories
        ),
        fields='__all__'
    )


class BaseSectionInline(NestedStackedInline):
    model = Section
    formset = inlineformset_factory(
        Section, Question,
        formset=unique_field_formset(('consecutive_number',)),
        fields='__all__'
    )
    extra = 0


class ChecklistSectionInline(BaseSectionInline):
    inlines = [ChecklistQuestionNestedInline, ]


class NestedResultChecklistAnswerPhotoInline(NestedTabularInline):
    model = ResultChecklistAnswerPhoto
    fields = ('image', 'image_location', 'happened_at')
    readonly_fields = ('image', 'image_location', 'happened_at')
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ResultChecklistAnswerInline(NestedStackedInline):
    model = ResultChecklistAnswer
    fields = ('id', 'question_text', 'choice')
    readonly_fields = ('id', 'question_text', 'choice')
    can_delete = False
    inlines = [NestedResultChecklistAnswerPhotoInline]
    ordering = ('question__consecutive_number',)

    def get_queryset(self, request):
        qs = super(ResultChecklistAnswerInline, self).get_queryset(request)
        return qs.select_related('answer', 'question').prefetch_related('photos')

    def has_add_permission(self, request, obj=None):
        return False

    def question_text(self, obj):
        return obj.question.text

    def choice(self, obj):
        return obj.answer.text


class ResultChecklistConfirmationPhotoInline(MaxNumInlinesMixin, admin.TabularInline):
    model = ResultChecklistConfirmationPhoto
    extra = 1


class ResultChecklistAnswerPhotoInline(MaxNumInlinesMixin, admin.TabularInline):
    model = ResultChecklistAnswerPhoto


class ChecklistAdmin(NestedModelAdmin):
    form = ChecklistForm
    inlines = [ChecklistSectionInline, ]
    list_display = ('title', )
    exclude = ('checklist_type', )


@admin.register(ResultChecklist)
class ResultChecklistAdmin(Select2FiltersMixin, NestedModelAdmin):
    inlines = [ResultChecklistConfirmationPhotoInline, ResultChecklistAnswerInline]
    list_display = ('id', 'checklist', 'date_of_risk_assessment', 'is_correct', 'order', 'created_at', 'driver',)
    list_select_related = ('checklist', 'order', 'driver')
    list_filter = ('driver', 'checklist__checklist_type',)
    search_fields = ('id', 'driver__first_name', 'driver__last_name',)

    def get_queryset(self, request):
        return super(ResultChecklistAdmin, self).get_queryset(request) \
            .exclude(checklist__checklist_type=Checklist.SURVEY)


@admin.register(ResultChecklistAnswer)
class ResultChecklistAnswerAdmin(admin.ModelAdmin):
    inlines = [ResultChecklistAnswerPhotoInline, ]
    list_display = ('id', 'question', 'result_checklist', 'answer_text')
    list_select_related = ('result_checklist', 'answer', 'question')
    list_filter = ('result_checklist', 'answer__question__text')
    search_fields = ('id', )

    raw_id_fields = ('answer', 'result_checklist', 'question')
    autocomplete_lookup_fields = {
        'fk': ['result_checklist', ],
    }

    class Media:
        js = (
            'js/admin_filters_select2/jquery.init.js',
            'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/js/select2.min.js',
            'js/admin_filters_select2/admin_filters_select2.js',
            'js/lightbox2/js/lightbox.min.js',
        )
        css = {
            'all': ('js/lightbox2/css/lightbox.css',
                    'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/css/select2.min.css')
        }


@admin.register(ImageLocation)
class ImageLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'location', 'created_at', 'happened_at')

    readonly_fields = ('created_at',)
