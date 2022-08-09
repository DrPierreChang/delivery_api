# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-04-10 12:49
from __future__ import unicode_literals

from django.db import migrations


def create_sections_for_existing_checklists(apps, schema_editor):
    Checklist = apps.get_model('merchant_extension', 'Checklist')
    Section = apps.get_model('merchant_extension', 'Section')

    for checklist in Checklist.objects.all():
        section = Section.objects.create(checklist=checklist, title=checklist.title)
        checklist.questions.update(section=section)


def reverse_sections_to_checklists_migration(apps, schema_editor):
    Question = apps.get_model('merchant_extension', 'Question')

    for question in Question.objects.filter(checklist__isnull=False):
        question.checklist = question.section.checklist
        question.save()


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0011_auto_20190320_2321'),
    ]

    operations = [
        migrations.RunPython(
            code=create_sections_for_existing_checklists,
            reverse_code=reverse_sections_to_checklists_migration
        ),
    ]