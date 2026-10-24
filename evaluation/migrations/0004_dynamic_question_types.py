from django.db import migrations, models


def set_question_types(apps, schema_editor):
    Question = apps.get_model('evaluation', 'Question')
    for question in Question.objects.all():
        if question.question_number <= 5:
            question.question_type = 'omr'
        else:
            question.question_type = 'classical'
        question.save(update_fields=['question_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0003_alter_question_correct_answer_alter_question_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='sheet_layout',
            field=models.JSONField(blank=True, default=dict, verbose_name='Answer Sheet Layout'),
        ),
        migrations.AddField(
            model_name='question',
            name='question_type',
            field=models.CharField(
                choices=[('omr', 'Optical (OMR)'), ('classical', 'Classical (Score Box)')],
                default='omr',
                max_length=10,
                verbose_name='Question Type',
            ),
        ),
        migrations.AlterField(
            model_name='question',
            name='correct_answer',
            field=models.CharField(
                blank=True,
                choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E')],
                default='',
                max_length=1,
                verbose_name='Correct Answer',
            ),
        ),
        migrations.AlterField(
            model_name='studentanswer',
            name='correct_answer',
            field=models.CharField(max_length=50, verbose_name='Correct Answer / Max Score'),
        ),
        migrations.RunPython(set_question_types, migrations.RunPython.noop),
    ]
