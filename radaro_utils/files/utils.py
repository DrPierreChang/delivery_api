import uuid

from django.utils.deconstruct import deconstructible


@deconstructible
class BasePathGenerator(object):
    def __call__(self, instance, filename):
        raise NotImplemented()


class TemplatePathGenerator(BasePathGenerator):
    template = '{0}.{1}'

    def get_template(self, instance, filename):
        return self.template

    def get_filename(self, instance, filename):
        return filename

    def render_name(self, instance, filename, *args, **kwargs):
        return self.get_template(instance, filename).format(*args, **kwargs)

    def collect_path(self, instance, filename):
        file_extension = filename.split('.')[-1]
        return self.get_filename(instance, filename), file_extension

    def __call__(self, instance, filename):
        return self.render_name(instance, filename, *self.collect_path(instance, filename))


class ModelPathGenerator(TemplatePathGenerator):
    template = '{0}/{1}.{2}'

    def collect_path(self, instance, filename):
        base_path = super(ModelPathGenerator, self).collect_path(instance, filename)
        return (type(instance).__name__, ) + base_path


class UUIDPathGenerator(ModelPathGenerator):
    def get_filename(self, instance, filename):
        return str(uuid.uuid4())


get_upload_path = UUIDPathGenerator()


def delayed_task_upload(instance, filename):
    upl = getattr(instance, 'upload_path', None)
    if not upl:
        return get_upload_path(instance, filename)
    else:
        return upl(instance, filename)


__all__ = ['TemplatePathGenerator', 'BasePathGenerator', 'ModelPathGenerator', 'get_upload_path', 'delayed_task_upload']
