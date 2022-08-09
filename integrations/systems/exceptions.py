class BadResponseException(Exception):
    def __init__(self, message, status_code):
        self._message = message
        self._status_code = status_code

    def __str__(self):
        return "%s: %s" % (self._status_code, self._message)

    def __str__(self):
        return str(self.__str__())
