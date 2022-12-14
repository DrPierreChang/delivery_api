# Generated by Django 2.2.5 on 2022-02-17 10:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0080_merge_20220211_2023'),
    ]

    operations = [
        migrations.AlterField(
            model_name='member',
            name='language',
            field=models.CharField(choices=[('en-au', 'English (Australia)'), ('en-gb', 'English (Great Britain)'), ('en-us', 'English (US)'), ('fr-ca', 'French (Canada)'), ('fr-be', 'French (Belgium)'), ('nl-be', 'Dutch (Belgium)'), ('nl-nl', 'Dutch (Netherlands)'), ('ko', 'Korean'), ('ja', 'Japanese'), ('pt-pt', 'Portuguese (Portugal)'), ('es', 'Spanish')], default='en-au', help_text='Application language', max_length=10),
        ),
    ]
