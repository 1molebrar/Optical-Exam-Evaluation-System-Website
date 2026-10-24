import json
from django.db import models
from django.contrib.auth.models import User


class Student(models.Model):
    student_id = models.CharField(max_length=50, unique=True, verbose_name='Student ID')
    first_name = models.CharField(max_length=100, verbose_name='First Name')
    last_name = models.CharField(max_length=100, verbose_name='Last Name')
    email = models.EmailField(verbose_name='Email')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.student_id} - {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class University(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name='University Name')
    logo = models.ImageField(upload_to='university_logos/', blank=True, null=True, verbose_name='Logo')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='Course Code')
    name = models.CharField(max_length=200, verbose_name='Course Name')
    university = models.ForeignKey(University, on_delete=models.CASCADE, null=True, blank=True, related_name='courses', verbose_name='University')
    description = models.TextField(blank=True, verbose_name='Description')
    credit = models.PositiveIntegerField(default=3, verbose_name='Course Credit')
    ects = models.PositiveIntegerField(default=3, verbose_name='ECTS')
    instructor = models.CharField(max_length=200, blank=True, verbose_name='Instructor Name')
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='teaching_courses', verbose_name='Teacher (User)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name='Active')

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.course.code}"


class Exam(models.Model):
    title = models.CharField(max_length=200, verbose_name='Exam Title')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
    exam_date = models.DateField(verbose_name='Exam Date')
    duration_minutes = models.IntegerField(default=60, verbose_name='Duration (minutes)')
    sheet_layout = models.JSONField(default=dict, blank=True, verbose_name='Answer Sheet Layout')
    rules = models.TextField(blank=True, default="", help_text="Custom exam rules printed on the right side of the paper")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-exam_date']

    def __str__(self):
        return f"{self.title} ({self.course.code})"

    @property
    def omr_questions(self):
        return self.questions.filter(question_type='omr')

    @property
    def classical_questions(self):
        return self.questions.filter(question_type='classical')

    def refresh_sheet_layout(self):
        from evaluation.utils.layout_engine import compute_sheet_layout
        questions = list(self.questions.all().values('question_number', 'question_type', 'points'))
        self.sheet_layout = compute_sheet_layout(questions=questions)
        self.save(update_fields=['sheet_layout', 'updated_at'])
        return self.sheet_layout

    def get_sheet_layout(self):
        required = {'mcq_bubble_centers', 'classical_score_rects'}
        if self.sheet_layout and required.issubset(self.sheet_layout.keys()):
            return self.sheet_layout
        return self.refresh_sheet_layout()

    def is_answer_key_configured(self):
        """True when every OMR question has a valid bubble answer (A–E)."""
        omr = self.omr_questions
        if not omr.exists():
            return True
        return all(q.correct_answer in dict(Question.ANSWER_CHOICES) for q in omr)


class AnswerKey(models.Model):
    """Stores the uploaded answer key image and its processed data."""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='answer_keys')
    image = models.ImageField(upload_to='answer_keys/', verbose_name='Answer Key Image')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False, verbose_name='Processed')
    detected_answers = models.TextField(blank=True, verbose_name='Detected Answers (JSON)')

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"AnswerKey for {self.exam.title} ({self.uploaded_at.strftime('%Y-%m-%d %H:%M')})"


class Question(models.Model):
    TYPE_OMR = 'omr'
    TYPE_CLASSICAL = 'classical'
    QUESTION_TYPE_CHOICES = [
        (TYPE_OMR, 'Optical (OMR)'),
        (TYPE_CLASSICAL, 'Classical (Score Box)'),
    ]

    ANSWER_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('E', 'E'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_number = models.PositiveIntegerField(verbose_name='Question Number')
    question_type = models.CharField(
        max_length=10, choices=QUESTION_TYPE_CHOICES, default=TYPE_OMR, verbose_name='Question Type',
    )
    text = models.TextField(blank=True, default='', verbose_name='Question Text')
    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES, blank=True, default='', verbose_name='Correct Answer')
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, verbose_name='Point Value')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['question_number']
        unique_together = ['exam', 'question_number']

    def __str__(self):
        label = 'OMR' if self.question_type == self.TYPE_OMR else 'Classical'
        return f"Q{self.question_number} [{label}] - {self.exam.title}"

    @property
    def is_omr(self):
        return self.question_type == self.TYPE_OMR

    @property
    def is_classical(self):
        return self.question_type == self.TYPE_CLASSICAL


class ExamEnrollment(models.Model):
    """Students explicitly enrolled to take a specific exam."""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='exam_enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['exam', 'student']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.exam.title}"


class ExamPaper(models.Model):
    """One printable answer sheet per exam (shared by all enrolled students)."""
    exam = models.OneToOneField(Exam, on_delete=models.CASCADE, related_name='exam_paper')
    paper_code = models.CharField(max_length=50, unique=True, verbose_name='Paper Code')
    generated_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False, verbose_name='Used for Evaluation')
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True, verbose_name='QR Code')
    pdf_file = models.FileField(upload_to='exam_papers/', blank=True, null=True, verbose_name='PDF Paper')
    image_file = models.ImageField(
        upload_to='exam_papers/', blank=True, null=True, verbose_name='Answer Sheet Image (PNG)',
    )

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Paper {self.paper_code} - {self.exam.title}"

    def get_qr_data(self):
        """QR contains exam metadata for identification (no student info)."""
        layout = self.exam.get_sheet_layout()
        return json.dumps({
            'exam_id': self.exam.id,
            'exam_title': self.exam.title,
            'course_code': self.exam.course.code,
            'course_name': self.exam.course.name,
            'omr_count': layout.get('omr_count', 0),
            'classical_count': layout.get('classical_count', 0),
            'paper_code': self.paper_code,
        })


class ScannedPaper(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('needs_review', 'Needs Manual Review'),
        ('failed', 'Failed'),
    ]

    image = models.ImageField(upload_to='scanned_papers/', verbose_name='Scanned Image')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False, verbose_name='Processed')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')

    qr_data = models.TextField(blank=True, verbose_name='QR Data')
    qr_confidence = models.FloatField(default=0.0, verbose_name='QR Confidence')
    qr_success = models.BooleanField(default=False, verbose_name='QR Decoded')

    ocr_student_id = models.CharField(max_length=20, blank=True, verbose_name='OCR Student ID')
    ocr_confidence = models.FloatField(default=0.0, verbose_name='OCR Confidence')

    omr_confidence = models.FloatField(default=0.0, verbose_name='OMR Confidence')
    detected_answers = models.TextField(blank=True, verbose_name='Detected Answers (JSON)')

    matched_exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name='scanned_papers')
    matched_student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name='scanned_papers')

    needs_review = models.BooleanField(default=False, verbose_name='Needs Manual Review')
    review_notes = models.TextField(blank=True, verbose_name='Review Notes')

    class Meta:
        ordering = ['-uploaded_at']

    def get_result(self):
        try:
            return self.result
        except ExamResult.DoesNotExist:
            return None

    @property
    def qr_error_message(self):
        if not self.qr_data:
            return ''
        try:
            return json.loads(self.qr_data).get('error', '') or ''
        except (json.JSONDecodeError, TypeError):
            return ''

    def __str__(self):
        status_icon = {
            'pending': '⏳', 'processing': '🔄', 'completed': '✅',
            'needs_review': '⚠️', 'failed': '❌'
        }.get(self.status, '❓')
        return f"{status_icon} Scanned #{self.id} - {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"


class StudentAnswer(models.Model):
    """Per-question answer record for a scanned paper."""
    scanned_paper = models.ForeignKey(ScannedPaper, on_delete=models.CASCADE, related_name='student_answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='student_answers')
    detected_answer = models.CharField(max_length=1, blank=True, verbose_name='Detected Answer')
    correct_answer = models.CharField(max_length=50, verbose_name='Correct Answer / Max Score')
    is_correct = models.BooleanField(default=False, verbose_name='Is Correct')
    is_blank = models.BooleanField(default=False, verbose_name='Is Blank')
    is_multiple_mark = models.BooleanField(default=False, verbose_name='Multiple Marks')
    question_points = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, verbose_name='Question Points')
    earned_points = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name='Earned Points')
    confidence = models.FloatField(default=0.0, verbose_name='Detection Confidence')
    needs_review = models.BooleanField(default=False, verbose_name='Needs Review')

    class Meta:
        unique_together = ['scanned_paper', 'question']
        ordering = ['question__question_number']

    def __str__(self):
        return f"Q{self.question.question_number}: {self.detected_answer or 'BLANK'} ({'✓' if self.is_correct else '✗'})"


class ExamResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='results')
    scanned_paper = models.OneToOneField(ScannedPaper, on_delete=models.CASCADE, related_name='result')
    correct_count = models.PositiveIntegerField(default=0, verbose_name='Correct')
    wrong_count = models.PositiveIntegerField(default=0, verbose_name='Wrong')
    blank_count = models.PositiveIntegerField(default=0, verbose_name='Blank')
    multiple_mark_count = models.PositiveIntegerField(default=0, verbose_name='Multiple Marks')
    review_needed_count = models.PositiveIntegerField(default=0, verbose_name='Review Needed')
    total_questions = models.PositiveIntegerField(default=0)
    total_points = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name='Total Points')
    earned_points = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name='Earned Points')
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Score (out of 100)')
    answers = models.TextField(blank=True, verbose_name='Answer Details (JSON)')
    confidence = models.FloatField(default=0.0, verbose_name='Overall Confidence')
    needs_review = models.BooleanField(default=False, verbose_name='Needs Manual Review')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['exam', 'student']

    def __str__(self):
        review_tag = ' ⚠️' if self.needs_review else ''
        return f"{self.student.full_name} - {self.exam.title}: {self.earned_points}/{self.total_points}{review_tag}"

    def get_answers(self):
        if self.answers:
            return json.loads(self.answers)
        return []

    def get_section_summaries(self):
        mcq = {'correct': 0, 'total_points': 0.0, 'earned_points': 0.0, 'question_count': 0, 'pct': 0}
        classical = {'correct': 0, 'total_points': 0.0, 'earned_points': 0.0, 'question_count': 0, 'pct': 0}

        for ans in self.get_answers():
            q_num = ans.get('question_number', 0)
            is_classical = ans.get('section') == 'Classical' or ans.get('question_type') == 'classical'
            bucket = classical if is_classical else mcq

            bucket['question_count'] += 1
            bucket['total_points'] += float(ans.get('question_points', 0) or 0)
            bucket['earned_points'] += float(ans.get('earned_points', 0) or 0)
            if ans.get('is_correct'):
                bucket['correct'] += 1

        for bucket in (mcq, classical):
            if bucket['total_points'] > 0:
                bucket['pct'] = round(bucket['earned_points'] / bucket['total_points'] * 100)

        return {'mcq': mcq, 'classical': classical}
