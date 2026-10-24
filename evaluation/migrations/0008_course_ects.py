from django.db import migrations, models


def copy_credit_to_ects(apps, schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    for course in Course.objects.all():
        course.ects = course.credit
        course.save(update_fields=['ects'])


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0007_single_exam_paper'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='ects',
            field=models.PositiveIntegerField(default=3, verbose_name='ECTS'),
        ),
        migrations.RunPython(copy_credit_to_ects, migrations.RunPython.noop),
    ]
