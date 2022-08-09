import threading
import warnings


class SuspendWarningManager:
    def __init__(self, register):
        self.register = register

    def __enter__(self):
        self.register.should_suspend_warning = True

    def __exit__(self, *args, **kwargs):
        self.register.should_suspend_warning = False


class GoogleAPIMerchantRegistry:
    def __init__(self):
        self.merchant_registry = {}
        self.should_suspend_warning = False

    class RegistryContextManager:
        def __init__(self, register, merchant):
            self.register = register
            self.merchant = merchant

        def __enter__(self):
            self.register.merchant_registry[threading.current_thread()] = self.merchant

        def __exit__(self, *args, **kwargs):
            self.register.merchant_registry.pop(threading.current_thread(), None)

    def register(self, merchant):
        return GoogleAPIMerchantRegistry.RegistryContextManager(register=self, merchant=merchant)

    def get_merchant(self, thread=None):
        return self.merchant_registry.get(thread or threading.current_thread())

    def suspend_warning(self):
        return SuspendWarningManager(self)

    def get_google_api_channel(self):
        merchant = self.get_merchant()
        if merchant is not None:
            return merchant.merchant_identifier
        if self.should_suspend_warning:
            return
        warnings.warn("To use Google Maps API's channels feature you should register merchant!", UserWarning)


merchant_registry = GoogleAPIMerchantRegistry()
