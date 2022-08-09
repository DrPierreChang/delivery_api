from django.db.models import Q

from merchant_extension.models import (
    Answer,
    ResultChecklistAnswer,
    ResultChecklistAnswerPhoto,
    ResultChecklistConfirmationPhoto,
)
from radaro_utils.serializers.mixins import BaseUnpackMixin


class ResultChecklistConfirmationPhotosUnpackMixin(BaseUnpackMixin):
    def unpack_fields(self, validated_data):
        super(ResultChecklistConfirmationPhotosUnpackMixin, self).unpack_fields(validated_data)
        confirmation_photos = validated_data.pop('confirmation_photos', [])
        if confirmation_photos:
            confirmation_photos = [ResultChecklistConfirmationPhoto(result_checklist=self.instance, **item)
                                   for item in confirmation_photos]
            ResultChecklistConfirmationPhoto.objects.bulk_create(confirmation_photos)


class ResultChecklistAnswersUnpackMixin(BaseUnpackMixin):
    def unpack_fields(self, validated_data):
        super(ResultChecklistAnswersUnpackMixin, self).unpack_fields(validated_data)
        answers_data = validated_data.pop('result_answers', [])
        if not answers_data:
            return
        answer_photos = []
        for data in answers_data:
            photos = data.pop('photos', [])
            choice = data.pop('answer')['text']
            question = data.pop('question')['id']
            question_answer = Answer.objects.filter(
                Q(text=choice) | Q(text_as_bool=choice),
                question=question
            ).first()
            result_answer = ResultChecklistAnswer.objects.create(
                result_checklist=self.instance,
                question=question,
                answer=question_answer,
                **data
            )
            photos_for_create = [
                ResultChecklistAnswerPhoto(answer_object=result_answer, **item) for item in photos
            ]
            answer_photos.extend(photos_for_create)
        ResultChecklistAnswerPhoto.objects.bulk_create(answer_photos)


__all__ = ['ResultChecklistConfirmationPhotosUnpackMixin', 'ResultChecklistAnswersUnpackMixin']
