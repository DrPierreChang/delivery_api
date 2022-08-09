from django.contrib.admin.widgets import ForeignKeyRawIdWidget


class MerchantRawIdWidget(ForeignKeyRawIdWidget):

    def url_parameters(self):
        res = super().url_parameters()
        res['merchant__id__exact'] = self.attrs['object'].merchant_id
        return res
