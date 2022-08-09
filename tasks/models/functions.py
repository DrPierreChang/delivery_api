from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models


class ConcatCodesInfo(models.Func):
    template = '''
        (SELECT ARRAY_TO_STRING(
            ARRAY(SELECT tc.%(data_field)s
                  FROM tasks_terminatecode tc,
                       tasks_order_terminate_codes m2m
                  WHERE m2m.order_id=tasks_order.id
                    AND m2m.terminatecode_id=tc.id), ';'))
        '''

    output_field = models.CharField()


class FormatDuration(models.Func):
    template = '''
        (SELECT CASE WHEN totalseconds IS NULL
                        THEN NULL
                        ELSE CONCAT(
                            totalseconds / 3600, ':',
                            LPAD((MOD(totalseconds, 3600) / 60)::TEXT, 2, '0'), ':', 
                            LPAD(MOD(totalseconds, 60)::TEXT, 2, '0')
                        )
            END
        FROM CAST(EXTRACT(EPOCH FROM %(data_field)s) AS INT) totalseconds)
    '''
    output_field = models.CharField()


class ConcatLabelsInfo(models.Func):
    template = '''
        (SELECT ARRAY_TO_STRING(
            ARRAY(SELECT ml.%(data_field)s
                  FROM merchant_label ml,
                       tasks_order_labels m2m
                  WHERE m2m.order_id=tasks_order.id
                    AND m2m.label_id=ml.id), ';'))
        '''

    output_field = models.CharField()

    def __init__(self, *expressions, **extra):
        super(ConcatLabelsInfo, self).__init__(*expressions, **extra)


class ConcatSkillSetsInfo(models.Func):
    template = '''
        (SELECT ARRAY_TO_STRING(
            ARRAY(SELECT ml.%(data_field)s
                  FROM merchant_skillset ml,
                       tasks_order_skill_sets m2m
                  WHERE m2m.order_id=tasks_order.id
                    AND m2m.skillset_id=ml.id), ';'))
        '''

    output_field = models.CharField()

    def __init__(self, *expressions, **extra):
        super(ConcatSkillSetsInfo, self).__init__(*expressions, **extra)


class ConcatBarcodesInfo(models.Func):
    template = '''
        (SELECT ARRAY_TO_STRING(
            ARRAY(SELECT tasks_barcode.%(data_field)s
                  FROM tasks_barcode 
                  WHERE tasks_barcode.order_id=tasks_order.id
            ), ';'))
        '''

    output_field = models.CharField()

    def __init__(self, *expressions, **extra):
        super(ConcatBarcodesInfo, self).__init__(*expressions, **extra)


class SurveyResultsInfo(models.Func):
    template = """
        (select json_object_agg(question, answer order by question)
        from
        (select survey_result.id, survey_result.checklist_id, t1.question, t1.answer
        from merchant_extension_resultchecklist as survey_result
        join 
        (select q.text as question, sa.result_checklist_id, 
        coalesce(nullif(array_to_string(array_agg(a.text order by a.text),','), ''), sa.text) as answer
        from merchant_extension_question as q 
        join merchant_extension_resultchecklistanswer as sa on q.id=sa.question_id
        left join merchant_extension_answer as a on a.id = sa.answer_id 
        group by q.text, sa.result_checklist_id, sa.text) as t1
        on survey_result.id=t1.result_checklist_id) as t2
        where t2.id=tasks_order.customer_survey_id
        group by (id, checklist_id)
        order by (id, checklist_id))
    """

    output_field = JSONField()


class UUID(models.Func):

    def as_sql(self, compiler, connection, function=None, template=None, arg_joiner=None, **extra_context):
        return super(UUID, self).as_sql(
            compiler, connection,
            function='encode',
            template="rtrim(%(function)s(cast(tasks_order.%(expression)s as varchar)::bytea, 'base64'), '=')"
        )

    output_field = models.CharField()


class DateTimeToChar(models.Func):
    function = "to_char"
    tz = settings.TIME_ZONE
    date_format = 'DD/MM/YYYY HH24:MI:SS'

    template = "%(function)s(%(expressions)s AT TIME ZONE '%(tz)s', '%(date_format)s')"
    output_field = models.CharField()

    def as_sql(self, compiler, connection, function=None, template=None, arg_joiner=None, **extra_context):
        if 'tz' not in self.extra:
            extra_context['tz'] = self.tz
        if 'date_format' not in self.extra:
            extra_context['date_format'] = self.date_format
        return super(DateTimeToChar, self).as_sql(
            compiler, connection, function=None,
            template=None, arg_joiner=None, **extra_context
        )
