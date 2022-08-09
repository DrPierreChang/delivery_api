# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-03-19 09:29
from __future__ import unicode_literals

from django.core.files.base import ContentFile
from django.db import migrations


def migrate_question_answers_from_question_to_separate_model(apps, schema_editor):
    Question = apps.get_model('merchant_extension', 'Question')
    QuestionAnswer = apps.get_model('merchant_extension', 'QuestionAnswer')

    def question_answers_generator():
        for question in Question.objects.all():
            yield QuestionAnswer(question=question, text=str(question.correct_answer), is_correct=True)
            yield QuestionAnswer(question=question, text=str(not question.correct_answer))

    QuestionAnswer.objects.bulk_create(question_answers_generator())


def reverse_questions_migration(apps, schema_editor):
    QuestionAnswer = apps.get_model('merchant_extension', 'QuestionAnswer')

    for question_answer in QuestionAnswer.objects.filter(question__category=0, is_correct=True):
        question_answer.question.correct_answer = question_answer.text == 'True'
        question_answer.question.save()


def migrate_answers_to_result_checklist_answers(apps, schema_editor):
    Answer = apps.get_model('merchant_extension', 'Answer')
    ResultChecklistAnswer = apps.get_model('merchant_extension', 'ResultChecklistAnswer')

    def answers_generator():
        for answer in Answer.objects.all().select_related('question'):
            yield ResultChecklistAnswer(
                result_checklist=answer.result_checklist,
                question_answer=answer.question.answers.filter(text=str(answer.choice)).first(),
                text=answer.comment,
                created_at=answer.created_at
            )

    ResultChecklistAnswer.objects.bulk_create(answers_generator())


def reverse_migration_answers_to_result_checklist_answers(apps, schema_editor):
    Answer = apps.get_model('merchant_extension', 'Answer')
    ResultChecklistAnswer = apps.get_model('merchant_extension', 'ResultChecklistAnswer')

    def answers_generator():
        for res_answer in ResultChecklistAnswer.objects.select_related('question_answer')\
                .filter(question_answer__question__category=0):
            answer_choice = res_answer.question_answer.text == 'True'
            yield Answer(
                result_checklist=res_answer.result_checklist,
                question=res_answer.question_answer.question,
                choice=answer_choice,
                comment=res_answer.text,
                created_at=res_answer.created_at
            )

    Answer.objects.bulk_create(answers_generator())


def migrate_answer_photos(apps, schema_editor):
    AnswerPhoto = apps.get_model('merchant_extension', 'AnswerPhoto')
    ResultChecklistAnswer = apps.get_model('merchant_extension', 'ResultChecklistAnswer')
    ResultChecklistAnswerPhoto = apps.get_model('merchant_extension', 'ResultChecklistAnswerPhoto')

    def result_answer_photo_gen():
        for photo in AnswerPhoto.objects.all().select_related('answer_object'):
            result_answer_photo = ResultChecklistAnswerPhoto()
            photo_copy = ContentFile(photo.image.read())
            photo_copy.name = photo.image.name.split('/')[-1]
            result_answer_photo.image = photo_copy
            res_answer = ResultChecklistAnswer.objects.get(
                result_checklist_id=photo.answer_object.result_checklist_id,
                question_answer__question_id=photo.answer_object.question_id,
                question_answer__text=str(photo.answer_object.choice)
            )
            result_answer_photo.answer_object = res_answer
            yield result_answer_photo

    ResultChecklistAnswerPhoto.objects.bulk_create(result_answer_photo_gen())


def reverse_migrate_answer_photos(apps, schema_editor):
    Answer = apps.get_model('merchant_extension', 'Answer')
    AnswerPhoto = apps.get_model('merchant_extension', 'AnswerPhoto')
    ResultChecklistAnswerPhoto = apps.get_model('merchant_extension', 'ResultChecklistAnswerPhoto')

    def answer_photo_gen():
        for photo in ResultChecklistAnswerPhoto.objects.all().select_related('answer_object'):
            answer_photo = AnswerPhoto()
            photo_copy = ContentFile(photo.image.read())
            photo_copy.name = photo.image.name.split('/')[-1]
            answer_photo.image = photo_copy
            answer_choice = photo.answer_object.question_answer.text == 'True'
            res_answer = Answer.objects.get(
                result_checklist_id=photo.answer_object.result_checklist_id,
                question_id=photo.answer_object.question_answer.question_id,
                choice=answer_choice
            )
            answer_photo.answer_object = res_answer
            yield answer_photo

    AnswerPhoto.objects.bulk_create(answer_photo_gen())


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0008_auto_20190319_2026'),
    ]

    operations = [
        migrations.RunPython(
            code=migrate_question_answers_from_question_to_separate_model,
            reverse_code=reverse_questions_migration
        ),
        migrations.RunPython(
            code=migrate_answers_to_result_checklist_answers,
            reverse_code=reverse_migration_answers_to_result_checklist_answers
        ),
        migrations.RunPython(
            code=migrate_answer_photos,
            reverse_code=reverse_migrate_answer_photos
        )

    ]