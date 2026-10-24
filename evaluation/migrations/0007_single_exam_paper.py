from django.db import migrations, models
import django.db.models.deletion


def migrate_to_single_paper(apps, schema_editor):
    ExamPaper = apps.get_model('evaluation', 'ExamPaper')
    ExamEnrollment = apps.get_model('evaluation', 'ExamEnrollment')

    kept_exam_ids = set()
    for paper in ExamPaper.objects.order_by('id'):
        if paper.student_id:
            ExamEnrollment.objects.get_or_create(
                exam_id=paper.exam_id,
                student_id=paper.student_id,
            )
        if paper.exam_id in kept_exam_ids:
            paper.delete()
        else:
            kept_exam_ids.add(paper.exam_id)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0006_ensure_exampaper_image_file'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enrolled_at', models.DateTimeField(auto_now_add=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_enrollments', to='evaluation.exam')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_enrollments', to='evaluation.student')),
            ],
            options={
                'ordering': ['-enrolled_at'],
                'unique_together': {('exam', 'student')},
            },
        ),
        migrations.RunPython(migrate_to_single_paper, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='exampaper',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='exampaper',
            name='student',
        ),
        migrations.AlterField(
            model_name='exampaper',
            name='exam',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='exam_paper', to='evaluation.exam'),
        ),
        migrations.AlterField(
            model_name='exampaper',
            name='image_file',
            field=models.ImageField(blank=True, null=True, upload_to='exam_papers/', verbose_name='Answer Sheet Image (PNG)'),
        ),
    ]
