from distutils.util import strtobool

from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from merchant_extension.models import (
    Answer,
    Checklist,
    Question,
    ResultChecklist,
    ResultChecklistAnswer,
    ResultChecklistAnswerPhoto,
)
from radaro_utils.serializers.mobile.fields import ImageListField, NullResultMixin, RadaroMobileImageField
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer


class DescriptionImageSerializer(NullResultMixin, serializers.ModelSerializer):
    url = RadaroMobileImageField(read_only=True, source='description_image')
    thumbnail_url = RadaroMobileImageField(read_only=True, source='description_image')

    class Meta:
        model = Question
        fields = ('url', 'thumbnail_url')


class AnswerSerializer(RadaroMobileModelSerializer):
    choice = serializers.BooleanField()

    class Meta:
        model = Answer
        fields = ('id', 'choice', 'photos_required', 'is_correct')


class QuestionSerializer(RadaroMobileModelSerializer):
    description_image = DescriptionImageSerializer(source='*', read_only=True)
    answers = AnswerSerializer(many=True)

    class Meta:
        model = Question
        exclude = ('category', 'section', 'subtitles')


class ChecklistSerializer(RadaroMobileModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Checklist
        exclude = ('id', 'invite_text', 'thanks_text')


class ResultAnswerPhotoSerializer(NullResultMixin, serializers.ModelSerializer):
    url = RadaroMobileImageField(read_only=True, source='image')
    thumbnail_url = RadaroMobileImageField(read_only=True, source='thumb_image_100x100')

    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = ResultChecklistAnswerPhoto
        fields = ('url', 'thumbnail_url')


class AnswerChoiceField(serializers.Field):
    default_error_messages = {
        'invalid': _('A valid bool is required.')
    }

    def to_internal_value(self, data):
        try:
            data = bool(strtobool(data))
        except (ValueError, TypeError):
            self.fail('invalid')
        return data

    def to_representation(self, instance):
        return instance


class ResultAnswerSerializer(RadaroMobileModelSerializer):
    choice = AnswerChoiceField()
    answer_photos = ImageListField(required=False, write_only=True, default=[], source='photos')
    photos = ResultAnswerPhotoSerializer(many=True, read_only=True)

    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = ResultChecklistAnswer
        fields = ('id', 'question', 'choice', 'comment', 'answer_photos', 'photos')
        extra_kwargs = {'comment': {'source': 'text'}}

    def validate(self, attrs):
        valid_answers = [answer for answer in attrs['question'].answers.all() if answer.choice == attrs['choice']]
        answer = valid_answers and valid_answers[0] or None

        if answer is None:
            raise serializers.ValidationError(
                {'choice': _('Not a valid choice')}, code='invalid',
            )

        attrs.pop('choice', None)
        attrs['answer'] = answer
        return attrs

    def create(self, validated_data):
        answer_images = validated_data.pop('photos', [])
        validated_data.update(result_checklist=self.context['result_checklist'])

        exist_obj = ResultChecklistAnswer.objects.filter(
            result_checklist=validated_data['result_checklist'], question=validated_data['question']
        ).first()
        if exist_obj is not None:
            return exist_obj

        obj = super().create(validated_data)

        if answer_images:
            image_objects = []
            for image in answer_images:
                image_object = ResultChecklistAnswerPhoto(answer_object=obj, **image)
                image_object.prepare_exif(validated_data['result_checklist'].checklist_merchant)
                image_objects.append(image_object)
            ResultChecklistAnswerPhoto.objects.bulk_create(image_objects)

        return obj


class ResultChecklistSerializer(RadaroMobileModelSerializer):
    checklist = ChecklistSerializer(read_only=True)
    checklist_passed = serializers.BooleanField(read_only=True, source='is_passed')
    is_correct = serializers.SerializerMethodField()
    answers = ResultAnswerSerializer(many=True, source='result_answers')

    class Meta:
        model = ResultChecklist
        fields = ('id', 'checklist', 'answers', 'is_correct', 'checklist_passed',
                  'created_at', 'date_of_risk_assessment')

    def get_is_correct(self, instance):
        return instance.is_correct or False


class JobChecklistSerializer(serializers.ModelSerializer):
    checklist = ChecklistSerializer(read_only=True)
    is_correct = serializers.SerializerMethodField()

    class Meta:
        model = ResultChecklist
        fields = ('id', 'checklist', 'is_correct', 'checklist_passed', 'created_at',
                  'date_of_risk_assessment')
        extra_kwargs = {'checklist_passed': {'source': 'is_passed'}}

    def get_is_correct(self, instance):
        return instance.is_correct or False
