# Optical Exam Evaluation System - Technical Documentation

## 1. Class Diagram (Text-Based UML)

```
┌─────────────────┐       ┌─────────────────┐
│    Student      │       │     Course     │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ student_id      │       │ code            │
│ first_name      │       │ name            │
│ last_name       │       │ description     │
│ email           │       │ created_at      │
│ created_at      │       │ updated_at      │
└────────┬────────┘       └─────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────┐
│           Enrollment                  │
├───────────────────────────────────────┤
│ id (PK)                               │
│ student_id (FK) ◄──────┐              │
│ course_id (FK) ────────┼───────►      │
│ enrolled_at           │   1:1        │
│ is_active             │              │
└────────────────────────┘              │
                                       │
┌───────────────────────────────────────┐
│              Exam                     │
├───────────────────────────────────────┤
│ id (PK)                               │
│ course_id (FK) ◄──────────┐          │
│ title                    │          │
│ exam_date                │          │
│ duration_minutes         │          │
│ total_marks              │          │
└────────────┬────────────┘             │
             │ 1:N                      │
             ▼                          │
┌───────────────────────────────────────┐
│            Question                   │
├───────────────────────────────────────┤
│ id (PK)                               │
│ exam_id (FK) ◄────────────┐          │
│ question_number          │          │
│ text                     │          │
│ marks                    │          │
└──────────────────────────┘          │
                                     │
┌───────────────────────────────────────┐
│            ExamPaper                  │
├───────────────────────────────────────┤
│ id (PK)                               │
│ exam_id (FK) ◄──┐                     │
│ student_id (FK)│                     │
│ paper_code     │                     │
│ generated_at   │                     │
│ is_used        │                     │
└────────┬───────┘                     │
         │ 1:1                          │
         ▼                              │
┌───────────────────────────────────────┐
│          ScannedPaper                 │
├───────────────────────────────────────┤
│ id (PK)                               │
│ exam_paper_id (FK) ◄──┐               │
│ image                │               │
│ uploaded_at          │               │
│ processed            │               │
│ ocr_data             │               │
└────────┬─────────────┘               │
         │ 1:1                          │
         ▼                              │
┌───────────────────────────────────────┐
│        EvaluationResult               │
├───────────────────────────────────────┤
│ id (PK)                               │
│ exam_paper_id (FK) ◄──┐               │
│ evaluator_name       │               │
│ total_score          │               │
│ evaluated_at         │               │
│ notes                │               │
└────────┬─────────────┘               │
         │ 1:N                          │
         ▼                              │
┌───────────────────────────────────────┐
│          QuestionScore                │
├───────────────────────────────────────┤
│ id (PK)                               │
│ evaluation_id (FK) ◄──┐               │
│ question_id (FK)     │               │
│ score                │               │
│ feedback             │               │
└──────────────────────┘               │
```

## 2. Model Explanations

### Student
- Represents a student in the system
- Fields: student_id (unique), first_name, last_name, email
- Relationships: Has many Enrollments, has many ExamPapers

### Course
- Represents a university course
- Fields: code (unique), name, description
- Relationships: Has many Exams, has many Enrollments

### Enrollment
- Many-to-many relationship via intermediary model between Student and Course
- Fields: is_active status, enrolled_at timestamp
- Ensures each student can only enroll once per course

### Exam
- Represents an exam within a course
- Fields: title, exam_date, duration_minutes, total_marks (auto-calculated)
- Relationships: Belongs to Course, has many Questions, has many ExamPapers

### Question
- Individual questions within an exam
- Fields: question_number, text, marks
- Relationships: Belongs to Exam

### ExamPaper
- Generated exam paper for a specific student
- Fields: paper_code (unique), generated_at, is_used flag
- Relationships: Belongs to Exam and Student

### ScannedPaper
- Uploaded scanned image of an exam paper
- Fields: image (file), processed flag, ocr_data (JSON text)
- Relationships: One-to-one with ExamPaper

### EvaluationResult
- Stores the evaluation outcome
- Fields: evaluator_name, total_score, notes
- Relationships: One-to-one with ExamPaper, has many QuestionScores

### QuestionScore
- Individual question scores within an evaluation
- Fields: score, feedback
- Relationships: Belongs to EvaluationResult and Question

## 3. API Endpoints List

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/` | Home page |
| GET | `/students/` | List all students |
| POST | `/students/create/` | Create new student |
| GET | `/api/students/` | API: List students |
| POST | `/api/students/create/` | API: Create student |
| GET | `/courses/` | List all courses |
| POST | `/courses/create/` | Create new course |
| GET | `/api/courses/` | API: List courses |
| POST | `/api/courses/create/` | API: Create course |
| GET | `/enroll/` | Enrollment form |
| POST | `/enroll/` | Enroll student to course |
| POST | `/api/enroll/` | API: Enroll student |
| GET | `/exams/` | List all exams |
| POST | `/exams/create/` | Create new exam |
| POST | `/api/exams/create/` | API: Create exam |
| GET | `/exam-paper/<exam_id>/<student_id>/` | Generate exam paper |
| POST | `/api/exam-paper/<exam_id>/<student_id>/` | API: Generate paper |
| GET | `/upload/` | Upload scanned paper form |
| POST | `/upload/` | Upload scanned paper |
| POST | `/api/upload/` | API: Upload scanned paper |
| GET | `/process/<scanned_id>/` | Process scanned paper (OCR) |
| POST | `/api/process/` | API: Process scanned paper |
| GET | `/results/` | List evaluation results |
| GET | `/results/<result_id>/` | View evaluation detail |
| GET | `/results/create/` | Create evaluation form |
| GET | `/api/results/<result_id>/` | API: Get evaluation result |
| POST | `/api/results/create/` | API: Create evaluation |
| GET | `/export/` | Export all results as JSON |
| GET | `/export/<exam_id>/` | Export results for specific exam |
| GET | `/export/download/` | Download JSON file |
| GET | `/export/download/<exam_id>/` | Download JSON for exam |

## 4. Screenshots Placeholders

### Home Page
- Main dashboard with navigation cards
- Features: Student Management, Course Management, Exam Management, Enrollment, Scanned Papers, Evaluation

### Student List Page
- Table showing all students with ID, Name, Email, Created Date
- "Add New Student" button at top

### Student Form Page
- Form with fields: Student ID, First Name, Last Name, Email
- Submit and Cancel buttons

### Exam List Page
- Table showing all exams with Title, Course, Date, Duration, Total Marks, Question Count

### Exam Form Page
- Form with exam details and dynamic question addition
- Fields: Title, Course (dropdown), Date, Duration, Questions (add/remove)

### Evaluation Results Page
- Table showing all results with Paper Code, Student, Exam, Score, Percentage, Evaluator

### Exam Paper (Generated)
- Print-friendly layout with student info, questions, optical answer area, score boxes

## 5. Full Python Code of Models

```python
# evaluation/models.py

from django.db import models


class Student(models.Model):
    """
    Represents a student in the system.
    """
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


class Course(models.Model):
    """
    Represents a course in the university.
    """
    code = models.CharField(max_length=20, unique=True, verbose_name='Course Code')
    name = models.CharField(max_length=200, verbose_name='Course Name')
    description = models.TextField(blank=True, verbose_name='Description')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Enrollment(models.Model):
    """
    Represents the relationship between a student and a course.
    Many-to-many relationship via this intermediary model.
    """
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
    """
    Represents an exam within a course.
    """
    title = models.CharField(max_length=200, verbose_name='Exam Title')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
    exam_date = models.DateField(verbose_name='Exam Date')
    duration_minutes = models.IntegerField(default=60, verbose_name='Duration (minutes)')
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Total Marks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-exam_date']

    def __str__(self):
        return f"{self.title} ({self.course.code})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.total_marks = sum(q.marks for q in self.questions.all())
        super().save(update_fields=['total_marks'])


class Question(models.Model):
    """
    Represents a question within an exam.
    """
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_number = models.PositiveIntegerField(verbose_name='Question Number')
    text = models.TextField(verbose_name='Question Text')
    marks = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Marks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['question_number']
        unique_together = ['exam', 'question_number']

    def __str__(self):
        return f"Q{self.question_number} - {self.exam.title}"


class ExamPaper(models.Model):
    """
    Represents a generated exam paper for a student.
    Contains all the exam details, student info, and a unique identifier.
    """
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='exam_papers')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_papers')
    paper_code = models.CharField(max_length=50, unique=True, verbose_name='Paper Code')
    generated_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False, verbose_name='Used for Evaluation')

    class Meta:
        unique_together = ['exam', 'student']
        ordering = ['-generated_at']

    def __str__(self):
        return f"Paper {self.paper_code} - {self.student.full_name}"


class ScannedPaper(models.Model):
    """
    Represents an uploaded scanned exam paper.
    """
    exam_paper = models.OneToOneField(ExamPaper, on_delete=models.CASCADE, related_name='scanned_paper')
    image = models.ImageField(upload_to='scanned_papers/', verbose_name='Scanned Image')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False, verbose_name='Processed')
    ocr_data = models.TextField(blank=True, verbose_name='OCR Data')

    def __str__(self):
        return f"Scanned - {self.exam_paper.paper_code}"


class EvaluationResult(models.Model):
    """
    Represents the evaluation result of a scanned exam paper.
    """
    exam_paper = models.OneToOneField(ExamPaper, on_delete=models.CASCADE, related_name='evaluation_result')
    evaluator_name = models.CharField(max_length=100, blank=True, verbose_name='Evaluator')
    total_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Total Score')
    evaluated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, verbose_name='Notes')

    class Meta:
        ordering = ['-evaluated_at']

    def __str__(self):
        return f"Result - {self.exam_paper.paper_code}: {self.total_score}/{self.exam_paper.exam.total_marks}"


class QuestionScore(models.Model):
    """
    Represents the score for each individual question in an evaluation.
    """
    evaluation = models.ForeignKey(EvaluationResult, on_delete=models.CASCADE, related_name='question_scores')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='scores')
    score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Score')
    feedback = models.TextField(blank=True, verbose_name='Feedback')

    class Meta:
        unique_together = ['evaluation', 'question']

    def __str__(self):
        return f"Q{self.question.question_number}: {self.score}/{self.question.marks}"
```

## 6. Full Python Code of Views

```python
# evaluation/views.py (Simplified Overview)

import json
import random
import string
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from .models import (
    Student, Course, Enrollment, Exam, Question, 
    ExamPaper, ScannedPaper, EvaluationResult, QuestionScore
)

# Helper function to generate unique paper codes
def generate_paper_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# OCR Simulation function
def simulate_ocr(scanned_paper):
    """Simulate OCR by extracting data from the scanned paper."""
    exam_paper = scanned_paper.exam_paper
    exam = exam_paper.exam
    student = exam_paper.student
    
    ocr_data = {
        'student_id': student.student_id,
        'student_name': student.full_name,
        'exam_title': exam.title,
        'course_code': exam.course.code,
        'paper_code': exam_paper.paper_code,
        'questions': []
    }
    
    for question in exam.questions.all():
        max_marks = float(question.marks)
        simulated_score = random.uniform(0, max_marks)
        
        ocr_data['questions'].append({
            'question_number': question.question_number,
            'text': question.text,
            'max_marks': max_marks,
            'score': round(simulated_score, 2),
            'answer_detected': f"Answer for Q{question.question_number}"
        })
    
    scanned_paper.ocr_data = json.dumps(ocr_data)
    scanned_paper.processed = True
    scanned_paper.save()
    
    return ocr_data

# Views include:
# - index: Home page with navigation
# - student_list, student_create: Student management
# - course_list, course_create: Course management  
# - enroll_student: Enrollment functionality
# - exam_list, exam_create: Exam management
# - generate_exam_paper: Generate printable exam papers
# - upload_scanned_paper: Upload scanned answer sheets
# - process_scanned_paper: OCR simulation and processing
# - get_evaluation_results, get_evaluation_result: View results
# - create_evaluation_result: Create evaluation from OCR data
# - export_results_json: Export results in JSON format
```

## 7. Key Features Summary

1. **Student Management**: Create and list students with unique IDs
2. **Course Management**: Create courses with codes and descriptions
3. **Enrollment**: Enroll students to courses (many-to-many)
4. **Exam Creation**: Create exams with questions and marks
5. **Exam Paper Generation**: Generate printable exam papers with optical form areas
6. **Scanned Paper Upload**: Upload scanned answer sheets
7. **OCR Simulation**: Simulate extracting data from scanned images
8. **Evaluation Results**: View and manage evaluation results
9. **JSON Export**: Export structured data in JSON format

## 8. Database Schema

- 9 models total with proper foreign key relationships
- SQLite as default database
- Auto-generated migrations for all models
- Proper indexes on foreign keys and unique fields