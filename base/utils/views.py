from base.utils.db_routers import use_readonly_db


class ReadOnlyDBActionsViewSetMixin(object):
    read_only_db_actions = ['metadata', 'list', 'retrieve']

    def __getattribute__(self, name):
        if name in ['read_only_db_actions']:
            return super().__getattribute__(name)

        if name in self.read_only_db_actions:
            return use_readonly_db(super().__getattribute__(name))

        return super().__getattribute__(name)
