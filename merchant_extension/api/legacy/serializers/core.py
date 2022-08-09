from distutils.util import strtobool

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from base.models import Member
from merchant.validators import MerchantsOwnValidator
from merchant_extension.models import (
    Checklist,
    Question,
    ResultChecklist,
    ResultChecklistAnswer,
    ResultChecklistAnswerPhoto,
)
from radaro_utils.helpers import validate_photos_count
from radaro_utils.serializers.fields import Base64ImageField
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map
from tasks.api.legacy.serializers.core import OrderPreConfirmationPhotoSerializer

from .mixins import ResultChecklistAnswersUnpackMixin, ResultChecklistConfirmationPhotosUnpackMixin


class QuestionSerializer(serializers.ModelSerializer):
    description_image = Base64ImageField(allow_null=True, required=False)
    correct_answer = serializers.ReadOnlyField()

    class Meta:
        model = Question
        exclude = ('category', 'section')


class AnswerPhotoSerializer(serializers.ModelSerializer):
    image = Base64ImageField(allow_null=True)

    class Meta:
        model = ResultChecklistAnswerPhoto
        fields = ('image',)


class AnswerChoiceField(serializers.Field):
    def to_internal_value(self, data):
        return data

    def to_representation(self, instance):
        return bool(strtobool(instance))


class AnswerSerializer(serializers.ModelSerializer):
    photos = AnswerPhotoSerializer(many=True, required=False)
    choice = AnswerChoiceField(source='answer.text')
    comment = serializers.CharField(required=False, allow_blank=True, source='text')
    question = serializers.PrimaryKeyRelatedField(source='question.id', queryset=Question.objects.all())

    class Meta:
        model = ResultChecklistAnswer
        fields = ('id', 'choice', 'comment', 'question', 'photos')

    def validate_photos(self, attr):
        if attr is not None:
            return validate_photos_count(attr)


class ChecklistSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Checklist
        exclude = ('id', 'invite_text', 'thanks_text')


class ResultChecklistSerializer(
        ResultChecklistAnswersUnpackMixin,
        ResultChecklistConfirmationPhotosUnpackMixin,
        serializers.ModelSerializer):

    answers = AnswerSerializer(many=True, required=False, source='result_answers')
    checklist = ChecklistSerializer(read_only=True)
    confirmation_signature = serializers.SerializerMethodField()
    confirmation_photos = serializers.SerializerMethodField()
    confirmation_comment = serializers.SerializerMethodField()
    checklist_confirmed = serializers.SerializerMethodField()
    checklist_passed = serializers.SerializerMethodField()

    class Meta:
        model = ResultChecklist
        fields = (
            'id', 'checklist', 'answers',
            'is_correct', 'confirmation_signature',
            'confirmation_photos', 'confirmation_comment',
            'checklist_confirmed', 'checklist_passed',
            'created_at', 'date_of_risk_assessment', 'driver'
        )

    def validate_answers(self, value):
        if self.instance.result_answers.exists():
            raise ValidationError("You have already passed checklist.")
        return value

    def validate(self, attrs):
        if self.instance.is_confirmed:
            raise ValidationError("Checklist has been already confirmed.")
        return attrs

    def get_checklist_confirmed(self, instance):
        return instance.is_confirmed

    def get_checklist_passed(self, instance):
        return instance.is_passed

    def validate_confirmation_photos(self, attr):
        if attr is not None:
            return validate_photos_count(attr)

    def get_confirmation_signature(self, instance):
        confirmation_signature = (hasattr(instance, 'order') and instance.order.pre_confirmation_signature)\
                                 or instance.confirmation_photos
        if not confirmation_signature:
            return
        return Base64ImageField(allow_null=True, required=False).to_representation(confirmation_signature)

    def get_confirmation_photos(self, instance):
        confirmation_photos = (hasattr(instance, 'order') and instance.order.pre_confirmation_photos)\
                               or instance.confirmation_photos
        if not confirmation_photos:
            return
        return OrderPreConfirmationPhotoSerializer(confirmation_photos, many=True).data

    def get_confirmation_comment(self, instance):
        return (hasattr(instance, 'order') and instance.order.pre_confirmation_comment) or instance.confirmation_comment


class RetrieveResultChecklistSerializer(ResultChecklistSerializer):

    class Meta(ResultChecklistSerializer.Meta):
        fields = ('id', 'is_correct', 'checklist_confirmed', 'checklist_passed')


class ExternalQuestionSerializer(QuestionSerializer):

    class Meta:
        model = Question
        fields = ('description_image', 'text', 'description', 'correct_answer')


class ExternalChecklistSerializer(ChecklistSerializer):
    merchant_id = serializers.IntegerField()
    questions = ExternalQuestionSerializer(many=True, read_only=True)


class ExternalRetrieveResultChecklistSerializer(ResultChecklistSerializer):
    class Meta(ResultChecklistSerializer.Meta):
        fields = ('is_correct', 'checklist_confirmed', 'checklist_passed')


@serializer_map.register_serializer
class ResultChecklistDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = ResultChecklist


class DailyChecklistRequestSerializer(serializers.Serializer):
    driver = serializers.PrimaryKeyRelatedField(
        queryset=Member.objects.all(),
        validators=[MerchantsOwnValidator('driver', merchant_field='current_merchant')]
    )


__all__ = ['AnswerSerializer',
           'ChecklistSerializer',
           'ExternalChecklistSerializer',
           'ExternalRetrieveResultChecklistSerializer',
           'QuestionSerializer',
           'ResultChecklistSerializer',
           'RetrieveResultChecklistSerializer',
           'DailyChecklistRequestSerializer', ]
