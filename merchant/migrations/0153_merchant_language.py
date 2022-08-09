# Generated by Django 2.2.5 on 2022-06-20 09:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0152_merge_20211205_0147'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='language',
            field=models.CharField(choices=[('en-au', 'English (Australia)'), ('en-gb', 'English (Great Britain)'), ('en-us', 'English (US)'), ('fr-ca', 'French (Canada)'), ('fr-be', 'French (Belgium)'), ('nl-be', 'Dutch (Belgium)'), ('nl-nl', 'Dutch (Netherlands)'), ('ko', 'Korean'), ('ja', 'Japanese'), ('pt-pt', 'Portuguese (Portugal)'), ('es', 'Spanish')], default='en-au', help_text='Language used for customer tracking and as a preferred language while searching job addresses', max_length=10),
        ),
    ]