def hash_locations(from_, to_):
    """ Hash locations string from one point to second point.
    :type from_: dict
    :type to_: dict
    """
    return hash('{},{}->{},{}'.format(*(list(from_.values()) + list(to_.values()))))


def hash_locations_to_str(from_, to_):
    """ Hash locations string from one point to second point.
    :type from_: dict
    :type to_: dict
    """
    return '{},{}->{},{}'.format(*(list(from_.values()) + list(to_.values())))


class DistanceMatrix(dict):
    """Dictionary that helps store distance and duration between points.

        >>> matrix = DistanceMatrix()
        >>> point_a = {'lat': '27.535353', 'lng': '53.272727'}
        >>> point_b = {'lat': '27.511111', 'lng': '53.299999'}
        >>> matrix[(point_a, point_b)] = {'duration': 1, 'distance': 2}  # from point A to point B
        >>> print(matrix[(point_a, point_b)])
        {'duration': 1, 'distance': 2}
    """

    def __init__(self, inp=None, hash_locations_function=hash_locations, **kwargs):
        super(DistanceMatrix, self).__init__(inp or {}, **kwargs)
        self.hash_locations_function = hash_locations_function

    def _transform_key(self, key):
        if isinstance(key, tuple):
            key = self.hash_locations_function(*key)
        return key

    def __setitem__(self, key, value):
        super(DistanceMatrix, self).__setitem__(self._transform_key(key), value)

    def __getitem__(self, key):
        return super(DistanceMatrix, self).__getitem__(self._transform_key(key))

    def get(self, k, d=None):
        return super(DistanceMatrix, self).get(self._transform_key(k), d)
