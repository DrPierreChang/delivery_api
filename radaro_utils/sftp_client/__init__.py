from django.conf import settings

import pysftp


class SFTPClient(object):

    def __init__(self):
        self.conn = None

    def __enter__(self):
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None
        self.conn = pysftp.Connection(settings.SFTP_SERVER, username=settings.SFTP_USER,
                                      password=settings.SFTP_PASSWORD, port=settings.SFTP_PORT,
                                      cnopts=cnopts)
        return self

    def __exit__(self, *args, **kwargs):
        self.conn.close()

    def upload_file(self, flo, remotepath):
        with flo as f:
            f.open()
            self.conn.putfo(f, remotepath)


class SFTPMerchantClient(SFTPClient):
    root_directory = 'miele_uploads'

    def __init__(self, merchant):
        super().__init__()
        self.merchant = merchant

    def __enter__(self):
        super().__enter__()
        merchant_directory = '{}/{}'.format(self.root_directory, self.merchant.survey_export_directory)
        self.conn.chdir(merchant_directory)
        return self
