from django.db import models
from django.db.models.fields.files import FieldFile


# This CustomDateTimeField doesn't rewrite value before save.
# Django's DateTimeField is rewriting value before save.
class CustomDateTimeField(models.DateTimeField):
    def pre_save(self, model_instance, add):
        current_value = getattr(model_instance, self.attname)
        if current_value is None:
            return super(CustomDateTimeField, self).pre_save(model_instance, add)
        return current_value


# This CustomFieldFile overrides size property cause in base FieldFile class
# it return wrong value in case when File was saved and then opened for writing.
# Try not to use this fields in case when you don't need to use size property.
class CustomFieldFile(FieldFile):
    @property
    def size(self):
        self._require_file()
        with self.storage.open(self.name, 'rb') as f:
            size = f.size
        return size


class CustomFileField(models.FileField):
    attr_class = CustomFieldFile
