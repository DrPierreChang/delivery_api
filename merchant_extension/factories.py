import factory


class ChecklistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.Checklist'

    title = factory.fuzzy.FuzzyText()


class StartOfDayChecklistFactory(ChecklistFactory):
    class Meta:
        model = 'merchant_extension.StartOfDayChecklist'


class EndOfDayChecklistFactory(ChecklistFactory):
    class Meta:
        model = 'merchant_extension.EndOfDayChecklist'


class SurveyFactory(ChecklistFactory):
    class Meta:
        model = 'merchant_extension.Survey'


class SectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.Section'


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.Question'

    section = factory.SubFactory(SectionFactory)
    text = factory.fuzzy.FuzzyText()


class ResultChecklistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.ResultChecklist'

    checklist = factory.SubFactory(ChecklistFactory)


class SurveyResultFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.SurveyResult'

    checklist = factory.SubFactory(ChecklistFactory)


class AnswerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.Answer'

    question = factory.SubFactory(QuestionFactory)


class ResultAnswerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant_extension.ResultChecklistAnswer'

    answer = factory.SubFactory(AnswerFactory)
    result_checklist = factory.SubFactory(ResultChecklistFactory)
