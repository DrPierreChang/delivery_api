from django.utils.html import format_html


def image_file(image, short_description='Image', width='auto', height='auto'):
    def image_thumb(self, obj):
        image = getattr(obj, image_thumb.image, None)
        image_src = '-'
        if image:
            image_src = u'<img width="{}" height="{}" src="{}" />'.format(width, height, image.url)
        return format_html(image_src)

    image_thumb.__dict__.update({'short_description': short_description,
                                 'image': image,
                                 'width': width,
                                 'height': height
                                 })
    return image_thumb


def related_images_gallery(related_name, image_field_name, short_description='Photos', link_text='View photos'):
    def image_link(self, obj):
        rel_manager = getattr(obj, image_link.related_name, None)

        if rel_manager is not None and rel_manager.all().exists():
            link = '<a class="example-image-link" href="{href}" data-lightbox="data-{id}">{text}</a>'
            rel_objects = rel_manager.all()

            first_image = getattr(rel_objects[0], image_field_name)
            first_link = link.format(href=first_image.url, id=obj.id, text=link_text)
            for rel_obj in rel_objects[1:]:
                image = getattr(rel_obj, image_field_name)
                first_link += link.format(href=image.url, id=obj.id, text='')
            return format_html(first_link)

        return '-'

    image_link.__dict__.update({'short_description': short_description,
                                'related_name': related_name,
                                'image_field_name': image_field_name,
                                'link_text': link_text})
    return image_link
