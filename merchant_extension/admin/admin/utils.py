from django.forms import models


def unique_field_formset(field_names):
    class UniqueFieldFormSet(models.BaseInlineFormSet):
        def clean(self):
            super(UniqueFieldFormSet, self).clean()
            if any(self.errors):
                return
            values = set()
            for form in self.forms:
                value = tuple([form.cleaned_data.get(field_name, '') for field_name in field_names])
                if value and value in values:
                    form.add_error(None, 'Duplicate values for "%s" are not allowed.' % str(field_names))
                values.add(value)

    return UniqueFieldFormSet


def filtered_question_category_formset(base_class, question_categories):
    class CategoryFilteredFormSet(base_class):

        def __init__(self, *args, **kwargs):
            super(CategoryFilteredFormSet, self).__init__(*args, **kwargs)
            self.form.base_fields['category'].choices = question_categories

    return CategoryFilteredFormSet
