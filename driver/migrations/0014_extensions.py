from django.db import migrations


def create_third_party_extension(apps, schema_editor):
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS cube; CREATE EXTENSION IF NOT EXISTS earthdistance;")


def drop_third_party_extension(apps, schema_editor):
    schema_editor.execute("DROP EXTENSION IF EXISTS cube; DROP EXTENSION IF EXISTS earthdistance;")


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0013_auto_20180223_2153'),
    ]

    operations = [
        migrations.RunPython(create_third_party_extension, reverse_code=drop_third_party_extension, atomic=True)
]