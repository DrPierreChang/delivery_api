from django import forms

from merchant.renderers import ScreenTextRenderer

SCREEN_TEXT_FIELDS = [('heading', 'Heading'), ('second_heading', 'Second heading'), ('sub_heading', 'Sub-heading')]
SCREEN_TEXT_FIELDS_KEYS = [key for key, label in SCREEN_TEXT_FIELDS]


class ScreenTextWidget(forms.MultiWidget):
    template_name = 'admin/screen_text.html'

    def __init__(self, attrs=None):
        widgets = [forms.TextInput(attrs={'label_text': label, 'style': 'width: 600px'})
                   for _, label in SCREEN_TEXT_FIELDS]
        super(ScreenTextWidget, self).__init__(widgets=widgets, attrs=attrs)

    def decompress(self, value):
        value = value or {}

        previews = ScreenTextRenderer(screen_text=value).render(context=ScreenTextRenderer.get_context_example())
        if previews:
            for subwidget, field in zip(self.widgets, SCREEN_TEXT_FIELDS_KEYS):
                subwidget.attrs['preview'] = previews.get(field, '')

        return [value.get(field) for field, _ in SCREEN_TEXT_FIELDS]


class ScreenTextField(forms.MultiValueField):
    widget = ScreenTextWidget

    def __init__(self, *args, **kwargs):
        fields = [forms.CharField(required=False) for _ in SCREEN_TEXT_FIELDS]
        super(ScreenTextField, self).__init__(fields=fields, required=False, require_all_fields=False, *args, **kwargs)

    def compress(self, data_list):
        return dict(zip([field for field, _ in SCREEN_TEXT_FIELDS], data_list))
