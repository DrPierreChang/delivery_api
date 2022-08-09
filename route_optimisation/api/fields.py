class CurrentMerchantDefault:
    merchant = None

    def set_context(self, serializer_field):
        self.merchant = serializer_field.context['request'].user.current_merchant

    def __call__(self):
        return self.merchant

    def __repr__(self):
        return self.__class__.__name__
