class ROError(Exception):
    def __init__(self, message=None, *args, **kwargs):
        super(ROError, self).__init__(message, *args, **kwargs)
        if not hasattr(self, 'message'):
            self.message = message
        self.fail_reason = self.message


class NoSolutionFoundError(ROError):
    pass
