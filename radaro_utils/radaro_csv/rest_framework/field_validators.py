from collections import OrderedDict

from django.db import models
from django.db.models import F
from django.db.models.functions import Cast

from rest_framework import fields, serializers

from radaro_utils.radaro_csv.exceptions import CSVColumnTypeMappingException, MissingRequiredHeadersException


class DjangoQSHeaderControl(object):
    def check_field(self, f, v):
        if isinstance(v, serializers.SerializerMethodField):
            self.real_field = f
            self.ignored.append(f)
        elif hasattr(v, 'source'):
            if v.source is not None:
                self.real_field = v.source.replace('.', '__')
            else:
                self.real_field = f
            self.obligatory.append(self.real_field)
        else:
            self.real_field = f
        self.values_mapping[self.real_field] = f

    def validate(self, mapper):
        pass

    def __init__(self, mapper):
        self.real_field = None
        self.values_mapping = OrderedDict()
        self.ignored = []
        self.obligatory = []


class FlattenStructureControl(object):
    def check_field(self, f, v):
        if isinstance(v, serializers.Serializer):
            raise Exception('CSV file cannot have nested serializers - it is always flatten.')

    def validate(self, mapper):
        pass

    def __init__(self, mapper):
        pass


class HeaderControl(object):
    optional_missing = None
    unknown_fields = None

    def validate(self, mapper):
        columns = mapper.columns
        _columns_set = set(columns)
        _missing_required = self.required - _columns_set
        if _missing_required:
            raise MissingRequiredHeadersException(fields=_missing_required)
        self.optional_missing = self.optional - _columns_set
        self.unknown_fields = _columns_set - self.required - self.optional

    def __init__(self, mapper):
        self.required = set()
        self.optional = set()
        self.all_columns = []

    def check_field(self, f, v):
        if isinstance(v, serializers.HiddenField):
            return

        if v.required:
            self.required.add(f)
        else:
            self.optional.add(f)
        self.all_columns.append(f)


class TypeMapperControl(object):
    type_map = {
        fields.CharField: str,
        fields.IntegerField: float,
        fields.FloatField: float,
        fields.DateTimeField: str
    }

    # Field typing of object according to serializer structure
    _type_mapping = None

    # Column typing of csv file
    _column_type_mapping = None

    def __init__(self, mapper):
        self.unknown_ftypes_as_str = True
        self._type_map = {}
        self._type_mapping = {}

    def update_type_map(self, update):
        self._type_map.update(update)

    def check_field(self, f, v):
        tp = type(v)
        try:
            c_type = self._type_map.get(tp, self.type_map[tp])
        except KeyError:
            if self.unknown_ftypes_as_str:
                c_type = str
            else:
                raise CSVColumnTypeMappingException(f)
        self._type_mapping[f] = c_type

    def validate(self, mapper):
        columns = mapper.original_columns
        self._column_type_mapping = {f: tp for f, tp in self._type_mapping.items() if f in columns}

    @property
    def type_mapping(self):
        return self._column_type_mapping


# During mapper initialization collect serializer fields and compose kwargs for QS update
# During backend preparation we can use this parameters
class QSParametersControl(DjangoQSHeaderControl):
    field_name_postfix = '_as_str_'

    def _extract_source_field(self, f, v):
        if hasattr(v, 'source'):
            if v.source is not None:
                self.real_field = v.source.replace('.', '__')
                return
        self.real_field = f

    def _annotate(self, f, v, annotation_field, annotation_fn):
        ann = self.params.get('annotate', {})
        ann[annotation_field] = annotation_fn(self.real_field)
        self.params['annotate'] = ann

    def check_field(self, f, v):
        self._extract_source_field(f, v)
        # Casting to string type can be provided through annotation
        # Annotation fields cannot repeat model field names
        # So give them temporary postfixes
        annotation_field = f
        if hasattr(self.model_class, f) or not isinstance(v, serializers.CharField):
            annotation_field += self.field_name_postfix
        if isinstance(v, serializers.SerializerMethodField):
            self.ignored.append(f)
            annotation_field = f
        elif isinstance(v, serializers.IntegerField):
            # Suppose 16 symbols enough to represent all integers in database
            # Django says that IntegerField is 4 byte, so it's 10 symbols at max
            self._annotate(f, v, annotation_field, lambda rf: Cast(rf, output_field=models.CharField(max_length=16)))
            self.obligatory.append(annotation_field)
        else:
            self._annotate(f, v, annotation_field, F)
            self.obligatory.append(annotation_field)
        self.values_mapping[annotation_field] = f

    def validate(self, mapper):
        pass

    @property
    def table_name(self):
        return self.model_class._meta.db_table

    def __init__(self, mapper):
        super(QSParametersControl, self).__init__(mapper)
        self.params = {}
        self.model_class = mapper.serializer.Meta.model
