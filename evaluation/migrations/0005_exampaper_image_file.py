from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0004_dynamic_question_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='exampaper',
            name='image_file',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='exam_papers/',
                verbose_name='Answer Sheet Image (PNG/JPEG)',
            ),
        ),
    ]
