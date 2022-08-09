from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from merchant_extension.models import Answer, Question, ResultChecklistAnswer, Section, Survey, SurveyResult
from radaro_utils.serializers.mixins import BaseUnpackMixin


class SurveyAnswerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Answer
        exclude = ('question', )


class SurveyQuestionSerializer(serializers.ModelSerializer):
    answers = SurveyAnswerSerializer(many=True)

    class Meta:
        model = Question
        exclude = ('section', )


class SurveySectionSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True)

    class Meta:
        model = Section
        exclude = ('checklist', )


class SurveySerializer(serializers.ModelSerializer):
    sections = SurveySectionSerializer(many=True)

    class Meta:
        model = Survey
        exclude = ('checklist_type', 'id')


class SurveyLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Survey
        fields = ('title', 'id', 'description')


class SurveyResultAnswersSerializer(serializers.ModelSerializer):

    class Meta:
        model = ResultChecklistAnswer
        fields = ('id', 'answer', 'text', 'created_at', 'question')


class SurveyResultAnswersUnpackMixin(BaseUnpackMixin):
    def unpack_fields(self, validated_data):
        super(SurveyResultAnswersUnpackMixin, self).unpack_fields(validated_data)
        answers_data = validated_data.pop('result_answers', [])
        if not answers_data:
            return

        def result_answers_generator(result_answers_data, result_checklist):
            for data in result_answers_data:
                yield ResultChecklistAnswer(result_checklist=result_checklist, **data)

        ResultChecklistAnswer.objects.bulk_create(
            result_answers_generator(answers_data, self.instance)
        )


class SurveyResultSerializer(SurveyResultAnswersUnpackMixin, serializers.ModelSerializer):
    survey = SurveySerializer(read_only=True, source='checklist')
    result_answers = SurveyResultAnswersSerializer(many=True, required=False)

    class Meta:
        model = SurveyResult
        fields = ('id', 'result_answers', 'created_at', 'survey', 'is_passed')

    def validate(self, attrs):
        if self.instance and self.instance.result_answers.exists():
            raise ValidationError("Survey has been already passed.")
        return attrs


class SurveyCSVDownloadRequestSerializer(serializers.Serializer):
    survey = serializers.PrimaryKeyRelatedField(queryset=Survey.objects.all())
    sub_branding_id = serializers.ListField(child=serializers.IntegerField(), required=False)
    date_from = serializers.DateTimeField()
    date_to = serializers.DateTimeField()


# Survey Results Retrieve Serializers

class QuestionRetrieveSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question
        fields = ('id', 'consecutive_number', 'text')


class SurveySectionRetrieveSerializer(serializers.ModelSerializer):
    questions = QuestionRetrieveSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ('title', 'consecutive_number', 'description', 'questions')


class SurveyRetrieveSerializer(serializers.ModelSerializer):
    sections = SurveySectionRetrieveSerializer(many=True, read_only=True)

    class Meta:
        model = Survey
        fields = ('title', 'description', 'sections')


class SurveyResultAnswerRetrieveSerializer(serializers.ModelSerializer):
    text = serializers.CharField(read_only=True, source='answer_text')

    class Meta:
        model = ResultChecklistAnswer
        fields = ('question', 'text')


class SurveyResultRetrieveSerializer(serializers.ModelSerializer):
    survey = SurveyRetrieveSerializer(read_only=True, source='checklist')
    result_answers = SurveyResultAnswerRetrieveSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyResult
        fields = ('id', 'created_at', 'survey', 'result_answers')
