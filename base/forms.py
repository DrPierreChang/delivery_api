from itertools import chain

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import make_password
from django.contrib.postgres.utils import prefix_validation_error
from django.forms.utils import ErrorList

from radaro_utils import helpers

from .models import Member
from .utils import MobileAppVersionsConstants


class EmployeeForm(forms.ModelForm):
    password_confirmation = forms.CharField(max_length=50, widget=forms.PasswordInput)
    password = forms.CharField(max_length=50, widget=forms.PasswordInput)

    class Meta:
        model = Member
        fields = ['email', 'phone', 'password', 'password_confirmation', 'avatar', 'first_name', 'last_name']

    def clean(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password_confirmation')

        if password1 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        password_validation.validate_password(password1, self.instance)
        self.cleaned_data['password'] = make_password(password1)
        return self.cleaned_data


class MobileAppVersionsWidget(forms.MultiWidget):
    template_name = 'mobile_app_versions/mobile_app_versions.html'
    required_text_message = 'This field cannot be empty'

    def __init__(self, attrs=None):
        widgets = []
        for app_type in MobileAppVersionsConstants.APP_TYPES:
            input_attrs = {'label_text': MobileAppVersionsConstants.WIDGET_LABEL_MAP[app_type], 'app_type': app_type}
            widgets.extend([forms.TextInput(attrs=input_attrs), forms.TextInput(attrs=input_attrs)])
        super(MobileAppVersionsWidget, self).__init__(widgets=widgets, attrs=attrs)

    def decompress(self, value):
        value = value or {}
        versions_by_app_type = [value.get(app_type, [None, None]) for app_type in MobileAppVersionsConstants.APP_TYPES]
        return list(chain.from_iterable(versions_by_app_type))

    def get_context(self, name, value, attrs):
        context = super(MobileAppVersionsWidget, self).get_context(name, value, attrs)
        if self.attrs['validation_errors_fired']['required']:
            for subwidget in context['widget']['subwidgets']:
                if subwidget['value'] is None:
                    subwidget['errors'] = ErrorList([self.required_text_message])
        return context


class MobileAppVersionsField(forms.MultiValueField):
    widget = MobileAppVersionsWidget
    default_error_messages = {
        'required': 'Fill all versions fields above',
    }

    def __init__(self, *args, **kwargs):
        # Field for tracking MultiValueField's validation errors
        self.validation_errors_fired = {
            'required': False
        }
        fields_count = len(MobileAppVersionsConstants.APP_TYPES) * 2
        fields = [forms.CharField() for _ in range(fields_count)]
        super(MobileAppVersionsField, self).__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        chunks_by_app_type = helpers.chunks(data_list, 2)
        return dict(list(zip(MobileAppVersionsConstants.APP_TYPES, chunks_by_app_type)))

    def widget_attrs(self, widget):
        attrs = super(MobileAppVersionsField, self).widget_attrs(widget)
        attrs['validation_errors_fired'] = self.validation_errors_fired
        return attrs

    def clean(self, value):
        try:
            return super(MobileAppVersionsField, self).clean(value)
        except forms.ValidationError as exc:
            if getattr(exc, 'code', None) == 'required':
                self.validation_errors_fired['required'] = True
            raise


class DynamicArrayWidget(forms.TextInput):

    template_name = 'dynamic_array/dynamic_array.html'

    def get_context(self, name, value, attrs):
        value = value or ['']
        context = super(DynamicArrayWidget, self).get_context(name, value, attrs)
        final_attrs = context['widget']['attrs']
        id_ = context['widget']['attrs'].get('id')

        subwidgets = []
        for index, item in enumerate(context['widget']['value']):
            widget_attrs = final_attrs.copy()
            if id_:
                widget_attrs['id'] = '%s_%s' % (id_, index)
            widget = forms.TextInput()
            widget.is_required = self.is_required
            subwidgets.append(widget.get_context(name, item, widget_attrs)['widget'])

        context['widget']['subwidgets'] = subwidgets
        return context

    def value_from_datadict(self, data, files, name):
        getter = getattr(data, 'getlist', 'get')
        return getter(name)

    def format_value(self, value):
        return value or []


class CustomArrayField(forms.Field):
    def __init__(self, base_field, error_messages={}, **kwargs):
        error_msgs = {
            'item_invalid': 'Item %(nth)s is incorrect: ',
        }
        self.base_field = base_field
        self.max_length = kwargs.pop('max_length', None)
        error_msgs.update(error_messages)
        kwargs.setdefault('widget', DynamicArrayWidget)
        super(CustomArrayField, self).__init__(error_messages=error_msgs, **kwargs)

    def clean(self, value):
        cleaned_data = []
        errors = []
        value = [_f for _f in value if _f]
        for index, item in enumerate(value, start=1):
            try:
                cleaned_data.append(self.base_field.clean(item))
            except forms.ValidationError as error:
                errors.append(prefix_validation_error(
                    error, self.error_messages['item_invalid'],
                    code='item_invalid', params={'nth': index},
                ))
        if errors:
            raise forms.ValidationError(list(chain.from_iterable(errors)))
        # if cleaned_data and self.required:
        #     raise forms.ValidationError(self.error_messages['required'])
        return cleaned_data


class CustomEmailArrayField(CustomArrayField):
    def __init__(self, **kwargs):
        error_msgs = {
            'unique': 'Emails must be unique'
        }
        super(CustomEmailArrayField, self).__init__(base_field=forms.EmailField(), error_messages=error_msgs, **kwargs)

    def clean(self, value):
        cleaned_data = super(CustomEmailArrayField, self).clean(value)
        lower_emails = [email.lower() for email in cleaned_data]
        if len(lower_emails) != len(set(lower_emails)):
            raise forms.ValidationError(self.error_messages['unique'])
        return cleaned_data
