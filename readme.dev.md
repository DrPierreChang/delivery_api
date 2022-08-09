## Mobile API

####  Null instead of empty values
Instead of these empty values:
```
{
    "char_field": "",
    "array_field": [],
    "image_field": {
        "url": None,
        "thumbnail_url": None
    }
}
```
Should return next data:
```
{
    "char_field": None,
    "array_field": None,
    "image_field": None
}

```
To implement such behavior use:
1. NullResultMixin for image serializers where could be result like {"url": None, "thumbnail_url": None}.
2. RadaroMobileCharField to replace default CharField.
3. RadaroMobileModelSerializer to replace default ModelSerializer.
4. Set `list_serializer_class = RadaroMobileListSerializer` for serializers that could use `many=True` option.

Note! Use it only in mobile api.
