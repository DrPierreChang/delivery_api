class EditableManagerDefaultsMixin(object):
    MILES = 1609.344
    KM = 1000.0

    distances = (
        (MILES, 'Miles'),
        (KM, 'Kilometers')
    )

    BIG_ENDIAN = 'BE'
    LITTLE_ENDIAN = 'LE'
    MIDDLE_ENDIAN = 'ME'

    date_formats = (
        (BIG_ENDIAN, 'ISO format (YYYY-MM-DD)'),
        (LITTLE_ENDIAN, 'Europe format (DD/MM/YYYY)'),
        (MIDDLE_ENDIAN, 'USA format (MM/DD/YYYY)')
    )

    distance_aliases = {MILES: 'mi', KM: 'km'}
