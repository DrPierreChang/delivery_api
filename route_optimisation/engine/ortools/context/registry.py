class AssignmentContextManager(object):
    def __init__(self, params, assignment_context_class):
        self.assignment_context_class = assignment_context_class
        self.params = params

    def __enter__(self):
        current_context.set_context(self.assignment_context_class(self.params))
        return current_context

    def __exit__(self, exc_type, exc_val, exc_tb):
        current_context.set_context(None)


class CurrentAssignmentContext(object):
    def __init__(self):
        self._context = None

    def set_context(self, value):
        self._context = value

    def set_attr(self, attr, value):
        if self._context:
            setattr(self._context, attr, value)

    def __getattr__(self, item):
        if self._context is None:
            raise Exception('Assignment Context is not initialized')
        if hasattr(self._context, item):
            return getattr(self._context, item)
        raise Exception('Seems that assignment context does not have attribute `%s`' % item)


current_context = CurrentAssignmentContext()
