from django import forms
from django.contrib.postgres.forms import JSONField
from django.forms import ModelChoiceField

from route_optimisation.admin.widgets import LogWidget
from route_optimisation.models import EngineRun, ROLog, RouteOptimisation


class AdminLogField(ModelChoiceField):
    widget = LogWidget()

    def __init__(self, **kwargs):
        super().__init__(queryset=ROLog.objects.all(), **kwargs)
        self.optimisation_log = None

    def prepare_value(self, value):
        return self.optimisation_log.log


class RouteOptimisationForm(forms.ModelForm):
    optimisation_log = AdminLogField(disabled=True)

    class Meta:
        model = RouteOptimisation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['optimisation_log'].optimisation_log = self.instance.optimisation_log
        self.fields['optimisation_log'].widget.optimisation = self.instance


class AdminEngineOptionsField(JSONField):
    def prepare_value(self, value):
        return value.to_dict() if value is not None else None


class AdminEngineResultField(JSONField):
    def prepare_value(self, value):
        return value.to_dict() if value is not None else None


class EngineRunForm(forms.ModelForm):
    engine_log = AdminLogField(disabled=True)
    engine_options = AdminEngineOptionsField(disabled=True)
    result = AdminEngineResultField(disabled=True)

    class Meta:
        model = EngineRun
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['engine_log'].optimisation_log = self.instance.engine_log
        self.fields['engine_log'].widget.optimisation = self.instance
