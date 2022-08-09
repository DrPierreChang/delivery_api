from django.conf import settings
from storages.backends.azure_storage import AzureStorage


class PublicAzureStorage(AzureStorage):
    expiration_secs = None


class MediaRootAzureStorage(PublicAzureStorage):
    location = settings.MEDIA_FOLDER
    overwrite_files = False


class StaticRootAzureStorage(PublicAzureStorage):
    location = settings.STATIC_FOLDER
    overwrite_files = True
