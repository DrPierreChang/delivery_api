from datetime import datetime
from distutils.util import strtobool

from django import forms
from django.forms import ModelForm
from django.utils import timezone

from dateutil import relativedelta

from merchant.models import Merchant, SubBranding
from merchant_extension.models import Answer, Question, Survey


class AnswerForm(ModelForm):
    class Meta:
        model = Answer
        fields = '__all__'

    def clean(self):
        cleaned_data = super(AnswerForm, self).clean()
        question = cleaned_data.get('question', None)
        if question and question.category == Question.DICHOTOMOUS:
            answer_text = cleaned_data.get('text', '')
            try:
                strtobool(answer_text)
            except ValueError:
                error_msg = "Invalid value '{}'. Please, provide one " \
                            "of the following values: true/false, yes/no or 1/0"
                self.add_error('text', error_msg.format(answer_text))
        return cleaned_data


class JobAnswerForm(AnswerForm):
    pass


class StartOfDayAnswerForm(AnswerForm):
    class Meta:
        model = Answer
        exclude = ['photos_required']


class EndOfDayAnswerForm(AnswerForm):
    class Meta:
        model = Answer
        exclude = ['photos_required']


class SurveyAnswerForm(AnswerForm):
    class Meta:
        model = Answer
        exclude = ['photos_required']


# Need to be able to save images in nested forms
class ChecklistForm(ModelForm):
    def is_multipart(self):
        return True


class CMSSurveyResultsForm(forms.Form):
    date_from = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}),
        initial=lambda: timezone.now() + relativedelta.relativedelta(months=-1)
    )
    date_to = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}),
        initial=timezone.now
    )
    survey = forms.ModelChoiceField(queryset=Survey.objects.all())
    merchant = forms.ModelMultipleChoiceField(queryset=Merchant.objects.all(), required=False)
    sub_brand = forms.ModelMultipleChoiceField(queryset=SubBranding.objects.all(), required=False)

    def clean(self):
        cleaned_data = super(CMSSurveyResultsForm, self).clean()
        merchant = cleaned_data.get('merchant')
        sub_brand = cleaned_data.get('sub_brand')

        if not (merchant or sub_brand):
            raise forms.ValidationError(
                "Please, select at least one of "
                "the following fields: `Merchant`, `Sub brand`"
            )
        return cleaned_data

    def clean_date_to(self):
        date_to = self.cleaned_data.get('date_to')
        return date_to.replace(hour=23, minute=59, second=59)
