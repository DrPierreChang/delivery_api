class OptimisationValidError(Exception):
    def __init__(self, error_type):
        self.error = error_type


class MoveOrdersError(Exception):
    pass
