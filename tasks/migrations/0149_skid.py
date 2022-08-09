# Generated by Django 2.2.5 on 2020-07-23 08:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0148_auto_20200630_2017'),
    ]

    operations = [
        migrations.CreateModel(
            name='SKID',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('width', models.FloatField()),
                ('height', models.FloatField()),
                ('length', models.FloatField()),
                ('weight', models.FloatField()),
                ('quantity', models.IntegerField(default=1)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skids', to='tasks.Order')),
            ],
        ),
    ]