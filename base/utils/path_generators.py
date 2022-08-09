from radaro_utils.files.utils import TemplatePathGenerator


class ThumbnailsUploadPath(TemplatePathGenerator):
    template = 'thumbnails/{0}_100x100.{1}'

    def get_filename(self, instance, filename):
        return filename.split('.')[0]


get_upload_path_100x100 = ThumbnailsUploadPath()


class CustomUploadPath(TemplatePathGenerator):
    template = '{0}/{1}'

    def collect_path(self, instance, filename):
        return type(instance).__name__, instance.name_of_file


get_custom_upload_path = CustomUploadPath()
