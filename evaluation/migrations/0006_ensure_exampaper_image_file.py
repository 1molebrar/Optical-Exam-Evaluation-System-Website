from django.db import migrations


def ensure_image_file_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info(evaluation_exampaper)')
        columns = {row[1] for row in cursor.fetchall()}
        if 'image_file' not in columns:
            cursor.execute(
                'ALTER TABLE evaluation_exampaper '
                'ADD COLUMN image_file varchar(100) NULL'
            )


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0005_exampaper_image_file'),
    ]

    operations = [
        migrations.RunPython(ensure_image_file_column, migrations.RunPython.noop),
    ]
