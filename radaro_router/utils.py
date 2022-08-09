import sentry_sdk

from radaro_router import RadaroRouterClient


class DeliveryRouter(object):

    def __init__(self, token):
        self.token = token

    def __enter__(self):
        self.client = RadaroRouterClient(token=self.token)
        return self.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            sentry_sdk.capture_exception(exc_val)


class InstanceRadaroRouterSynchronizer(object):

    def __init__(self, router, action, extra=None):
        self.extra = extra or {}
        self.action = action
        self.router = router

    def __enter__(self):
        self.router.start_sync(self.action, self.extra)
        return self.router

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not (exc_type or self.router.synced):
            self.router.end_sync()
        return True
