from rest_framework import serializers

from base.models import Member
from merchant_extension.api.legacy.serializers.core import AnswerChoiceField
from merchant_extension.models import Checklist, Question, ResultChecklist, ResultChecklistAnswer
from tasks.models import Order
from webhooks.serializers import OrderFromExternalJobSerializer


class PhotoLocationSerializer(serializers.Serializer):
    location = serializers.CharField(read_only=True)


class PhotoSerializer(serializers.Serializer):
    image = serializers.ImageField(read_only=True)
    image_location = PhotoLocationSerializer(read_only=True, allow_null=True)
    happened_at = serializers.DateTimeField(read_only=True, allow_null=True)


class AnswerSerializer(serializers.ModelSerializer):
    photos = PhotoSerializer(many=True, read_only=True)
    choice = AnswerChoiceField(source='answer.text')
    comment = serializers.CharField(required=False, allow_blank=True, source='text')

    class Meta:
        model = ResultChecklistAnswer
        fields = ('choice', 'comment', 'photos')


class QuestionSerializer(serializers.ModelSerializer):
    description_image = serializers.ImageField(read_only=True)
    correct_answer = serializers.ReadOnlyField()
    answer = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ('description_image', 'correct_answer', 'text', 'description', 'subtitles', 'answer')

    def get_answer(self, instance):
        answers = ResultChecklistAnswer.objects.filter(
            question=instance,
            result_checklist=self.root.instance['result_checklist_info'],
        )
        answer = answers.first()
        return AnswerSerializer(answer).data if answer else None


class ChecklistSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Checklist
        fields = ('title', 'description', 'questions')


class ExternalResultChecklistSerializer(serializers.ModelSerializer):
    checklist = ChecklistSerializer(read_only=True)

    class Meta:
        model = ResultChecklist
        fields = ('created_at', 'checklist')


class ExternalChecklistEventsSerializer(serializers.Serializer):
    updated_at = serializers.DateTimeField()
    token = serializers.CharField(max_length=255)
    result_checklist_info = ExternalResultChecklistSerializer()
    topic = serializers.CharField(max_length=128)


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ('id', 'member_id')


class ExternalDailyChecklistEventsSerializer(ExternalChecklistEventsSerializer):
    driver_info = DriverSerializer()


class OrderSerializer(serializers.ModelSerializer):
    external_id = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'order_id', 'external_id', 'url')

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None

    def get_url(self, instance):
        return instance.get_order_url()


class ExternalJobChecklistEventsSerializer(ExternalChecklistEventsSerializer):
    job_info = OrderSerializer()


class ExternalJobChecklistEventsSerializerV2(ExternalChecklistEventsSerializer):
    order_info = OrderFromExternalJobSerializer()
