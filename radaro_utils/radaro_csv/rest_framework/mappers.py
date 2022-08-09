import copy
import re
from collections import OrderedDict

from django.utils.functional import cached_property

from radaro_utils.radaro_csv.mappers import BaseMapper
from radaro_utils.radaro_csv.mappers.pandas import PandasToDictMapper, QuerySetToDataFrameChunksMapper
from radaro_utils.radaro_csv.mappers.unicode_csv import BaseUnicodeCSVMapper
from radaro_utils.radaro_csv.rest_framework.field_validators import (
    FlattenStructureControl,
    HeaderControl,
    QSParametersControl,
)


class RestMapperMixin(object):
    # Serializer will be used to collect info about fields
    serializer = None

    field_validator_classes = (FlattenStructureControl, HeaderControl)
    field_validators = None

    _renamed_original_columns = None

    unknown_ftypes_as_str = False

    @property
    def csv_columns(self):
        raise NotImplementedError()

    @property
    def columns(self):
        raise NotImplementedError()

    def validate(self):
        for v in self.field_validators.values():
            v.validate(self)

    def prepare_field_validators(self):
        self.field_validators = OrderedDict()
        for Cl in self.field_validator_classes:
            self.field_validators[Cl] = Cl(self)

    def __init__(self):
        # Collecting stats from serializer
        self.prepare_field_validators()
        for f, v in self.serializer.get_fields().items():
            for validator in self.field_validators.values():
                validator.check_field(f, v)
        super(RestMapperMixin, self).__init__()


class RestReadMapper(RestMapperMixin, BaseMapper):
    _column_map = None

    @property
    def columns(self):
        return list(self._column_map.values())

    @property
    def csv_columns(self):
        raise NotImplementedError()

    def head_remapper(self, k):
        return self._column_map[k]

    def remapper(self, f):
        return re.sub(r'\*', '', re.sub(r' ', '_', f.lower()))

    # This is called during initialization of parser to open backend in a right way
    def prepare_columns(self, model_obj):
        self._column_map = OrderedDict((c, self.remapper(c)) for c in model_obj.columns)
        self.validate()
        return self.csv_columns


class PandasReadMapper(RestReadMapper, PandasToDictMapper):
    @property
    def csv_columns(self):
        unknown = self.field_validators[HeaderControl].unknown_fields
        return OrderedDict((orig, str) for orig, c in self._column_map.items() if c not in unknown)


class UnicodeCSVReadMapper(RestReadMapper, BaseUnicodeCSVMapper):
    @property
    def csv_columns(self):
        return self.columns

    @property
    def found_columns(self):
        unknown = self.field_validators[HeaderControl].unknown_fields
        return [c for c in self.columns if c not in unknown]


class QuerySetChunkMapper(RestMapperMixin, QuerySetToDataFrameChunksMapper):
    field_validator_classes = (FlattenStructureControl, QSParametersControl)

    def __init__(self, **kwargs):
        self.extra_fields = kwargs.pop('extra_fields', [])
        super(QuerySetChunkMapper, self).__init__()

    @cached_property
    def column_map(self):
        return self.field_validators[QSParametersControl]

    def head_remapper(self, f):
        return self.column_map.values_mapping[f]

    def update_qs(self, qs, context=None):
        params = copy.deepcopy(self.column_map.params)
        for func, func_kwargs in params.items():
            qs = getattr(qs, func)(**func_kwargs)
        return qs

    # Serializer fields that will be written to csv as headers
    def prepare_columns(self, file_obj):
        return list(self.column_map.values_mapping.values()) + self.extra_fields

    @property
    def columns(self):
        return self.column_map.obligatory
