from collections import defaultdict


class keydefaultdict(defaultdict):
    """
    Allows using the key value in the default dictionary

    Example:
    daily_jobs = keydefaultdict(lambda day: {
        'delivery_date': day,
        'route_optimisations': [],
        'orders': [],
    })

    daily_jobs['01-01-1970'] == {
        'delivery_date': '01-01-1970',
        'route_optimisations': [],
        'orders': [],
    }
    """

    def __missing__(self, key):
        result = self[key] = self.default_factory(key)
        return result
