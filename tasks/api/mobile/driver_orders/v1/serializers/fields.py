from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from markdown import markdown

from radaro_utils.serializers.mobile.fields import RadaroMobileCharField, RadaroMobilePrimaryKeyRelatedField


class CustomKeyWithMerchantRelatedField(RadaroMobilePrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        self.key_field = kwargs.pop('key_field', 'pk')
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(**{self.key_field: data})
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)

    def get_queryset(self):
        merchant_id = self.context['request'].user.current_merchant_id
        return super().get_queryset().filter(merchant_id=merchant_id)


class MarkdownField(RadaroMobileCharField):
    def to_representation(self, value):
        """
        Returns markdown string converted to html.
        """
        if not value:
            return super().to_representation(value)
        html = markdown(value, extensions=settings.MARKDOWN_EXTENSIONS)
        return format_html("<style>{}</style> {}", self.default_css, mark_safe(html))

    @property
    def default_css(self):
        style = "table, th, td {border: 1px solid black; border-collapse: collapse;} "\
                "table {width: 100%;}"
        return style
