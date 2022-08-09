class RadaroRouterClientException(Exception):

    def __init__(self, status_code, errors):
        self.errors = errors
        self.status_code = status_code

    def __str__(self):
        return 'An error occurred: status code {}, errors: {}'.format(self.status_code, self.errors)
