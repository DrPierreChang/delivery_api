import collections
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.forms import ImageField

from rest_framework import serializers
from rest_framework.fields import CharField, EmailField, empty
from rest_framework.relations import MANY_RELATION_KWARGS, ManyRelatedField

from PIL import Image

from radaro_utils.radaro_phone.serializers import RadaroPhoneField


class NullResultMixin:
    """
    Transforms incoming null-value into appropriate native value.
    Performs vice versa for outgoing result.
    """
    initial = None

    def run_validation(self, data=empty):
        if data is None and not self.allow_null:
            data = super().initial
        return super().run_validation(data)

    def to_representation(self, value):
        ret = super().to_representation(value)
        if not ret:
            return None
        # certain case in relation to a serializer field when it's preferable
        # to return None instead of a dictionary consisted of empty values
        if isinstance(ret, dict) and not any(ret.values()):
            return None
        return ret

    def get_initial(self):
        return self.initial


class RadaroMobileCharField(NullResultMixin, CharField):
    pass


class RadaroMobileEmailField(NullResultMixin, EmailField):
    pass


class RadaroMobilePhoneField(NullResultMixin, RadaroPhoneField):
    pass


class RadaroMobileManyRelatedField(NullResultMixin, ManyRelatedField):
    pass


class RadaroMobilePrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return RadaroMobileManyRelatedField(**list_kwargs)


class PreloadManyRelatedField(NullResultMixin, ManyRelatedField):
    preload_items = {}

    def to_internal_value(self, data):
        if isinstance(data, str) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        item_ids = [item for item in data if isinstance(item, int)]
        qs = self.child_relation.get_queryset().filter(id__in=item_ids)
        self.preload_items = {item.id: item for item in qs}

        return [
            self.child_relation.to_internal_value(item)
            for item in data
        ]


class RadaroMobilePrimaryKeyWithMerchantRelatedField(serializers.PrimaryKeyRelatedField):

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return PreloadManyRelatedField(**list_kwargs)

    def to_internal_value(self, data):
        if hasattr(self.parent, 'preload_items'):
            if not isinstance(data, int):
                self.fail('incorrect_type', data_type=type(data).__name__)
            elif data not in self.parent.preload_items.keys():
                self.fail('does_not_exist', pk_value=data)
            else:
                return self.parent.preload_items[data]
        else:
            return super().to_internal_value(data)

    def get_queryset(self):
        merchant_id = self.context['request'].user.current_merchant_id
        return super().get_queryset().filter(merchant_id=merchant_id)


class RadaroMobileDjangoImageField(ImageField):
    def to_python(self, data):
        f = super().to_python(data)

        if f.content_type in ['image/heic', 'image/heif', 'image/heif-sequence']:
            image_io = BytesIO()
            image = f.image
            if image.info.get('exif', None) is not None:
                image.convert('RGB').save(image_io, 'JPEG', exif=image.info['exif'])
            else:
                image.convert('RGB').save(image_io, 'JPEG')

            f = InMemoryUploadedFile(
                file=image_io,
                field_name=None,
                name=f.name + '.jpeg',
                content_type='image/jpeg',
                size=image_io.tell,
                charset=None,
                content_type_extra=f.content_type_extra,
            )
            f.image = Image.open(image_io)
            f.image.verify()
            if hasattr(f, 'seek') and callable(f.seek):
                f.seek(0)

        return f


class RadaroMobileImageField(serializers.ImageField):
    def __init__(self, *args, **kwargs):
        if '_DjangoImageField' not in kwargs:
            kwargs['_DjangoImageField'] = RadaroMobileDjangoImageField
        super().__init__(*args, **kwargs)


class ImageListField(serializers.ListField):
    child = RadaroMobileImageField()

    def to_internal_value(self, data):
        """
        List of dicts of native values <- List of dicts of primitive datatypes.
        """
        if isinstance(data, type('')) or isinstance(data, collections.Mapping) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        return [{'image': self.child.run_validation(item)} for item in data]

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return [
            self.child.to_representation(item.image) if item is not None else None
            for item in data.all()
        ]
