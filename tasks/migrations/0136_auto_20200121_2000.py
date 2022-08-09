# Generated by Django 2.2.5 on 2020-01-21 09:00

from django.db import migrations, models
import django.db.models.deletion

import radaro_utils.files.utils
import radaro_utils.models
import radaro_utils.radaro_phone.models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0135_order_deliver_address_2'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderPickUpConfirmationPhoto',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to=radaro_utils.files.utils.UUIDPathGenerator())),
            ],
            options={
                'abstract': False,
            },
            bases=(radaro_utils.models.ResizeImageMixin, models.Model),
        ),
        migrations.AddField(
            model_name='order',
            name='pick_up_confirmation_comment',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='pick_up_confirmation_signature',
            field=models.ImageField(blank=True, null=True, upload_to=radaro_utils.files.utils.UUIDPathGenerator()),
        ),
        migrations.AddField(
            model_name='orderpickupconfirmationphoto',
            name='order',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pick_up_confirmation_photos', to='tasks.Order'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[('not_assigned', 'Not assigned'), ('assigned', 'Assigned'), ('pickup', 'Pick up'),
                         ('picked_up', 'Picked up'), ('in_progress', 'In progress'), ('way_back', 'Way back'),
                         ('delivered', 'Completed'), ('failed', 'Failed')], default='not_assigned', max_length=20),
        )
    ]
