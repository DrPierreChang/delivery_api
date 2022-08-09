import re

from django.core.exceptions import ValidationError
from django.utils.translation import ngettext
from django.utils.translation import ugettext_lazy as _


class UpperCaseValidator(object):

    def __init__(self, min_letters=1):
        self.min_letters = min_letters

    def validate(self, password, user=None):
        if not re.search(r'[A-Z]{{{}}}'.format(self.min_letters), password):
            raise ValidationError(
                ngettext(
                    'The password must contain at least %(min_letters)d uppercase character',
                    'The password must contain at least %(min_letters)d uppercase characters',
                    self.min_letters
                )
                % {'min_letters': self.min_letters}
            )

    def get_help_text(self):
        return 'The password must contain uppercase letters.'


class LowerCaseValidator(object):

    def __init__(self, min_letters=1):
        self.min_letters = min_letters

    def validate(self, password, user=None):
        if not re.search(r'[a-z]{{{}}}'.format(self.min_letters), password):
            raise ValidationError(
                ngettext(
                    'The password must contain at least %(min_letters)d lowercase character',
                    'The password must contain at least %(min_letters)d lowercase characters',
                    self.min_letters
                )
                % {'min_letters': self.min_letters}
            )

    def get_help_text(self):
        return 'The password must contain lowercase letters.'


class HasNumberValidator(object):

    def __init__(self, min_numbers=1):
        self.min_numbers = min_numbers

    def validate(self, password, user=None):
        if not re.search(r'[0-9]{{{}}}'.format(self.min_numbers), password):
            raise ValidationError(
                ngettext(
                    'The password must contain at least %(min_numbers)d number',
                    'The password must contain at least %(min_numbers)d numbers',
                    self.min_numbers
                )
                % {'min_numbers': self.min_numbers}
            )

    def get_help_text(self):
        return 'The password must contain numbers.'
