class MissingRequiredHeadersException(Exception):
    def __init__(self, fields):
        self.fields = list(fields)


class TypeMappingException(Exception):
    pass


class SerializerFieldTypeMappingException(TypeMappingException):
    def __init__(self, type):
        self.type = type


class CSVColumnTypeMappingException(TypeMappingException):
    def __init__(self, column):
        self.column = column


class CSVEncodingError(Exception):
    def __str__(self):
        return 'Couldn\'t detect file encoding.'
