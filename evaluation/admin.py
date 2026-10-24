from django.contrib import admin
from django.contrib.admin import AdminSite
from .models import (
    Student, Course, Enrollment, ExamEnrollment, Exam, Question, AnswerKey,
    ExamPaper, ScannedPaper, StudentAnswer, ExamResult
)


class PinkAdminSite(AdminSite):
    site_header = '🎓 Optical Exam System - Admin'
    site_title = 'Admin Panel'
    index_title = 'Dashboard'

    login_template = 'admin/login.html'

    def each_context(self, request):
        context = super().each_context(request)
        context['site_url'] = '/'
        return context


class StudentAdmin(admin.ModelAdmin):
    list_display = ['student_id', 'first_name', 'last_name', 'email', 'created_at']
    search_fields = ['student_id', 'first_name', 'last_name', 'email']
    list_filter = ['created_at']


class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'credit', 'ects', 'instructor', 'created_at']
    search_fields = ['code', 'name', 'instructor']


class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'enrolled_at', 'is_active']
    list_filter = ['is_active', 'enrolled_at', 'course']
    search_fields = ['student__first_name', 'student__last_name', 'course__code']


class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'exam_date', 'duration_minutes', 'created_at']
    list_filter = ['exam_date', 'course']
    search_fields = ['title', 'course__code']


class QuestionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'question_number', 'question_type', 'correct_answer', 'points']
    list_filter = ['exam', 'question_type', 'correct_answer']
    search_fields = ['text']


class ExamEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'enrolled_at']
    list_filter = ['enrolled_at', 'exam']
    search_fields = ['student__first_name', 'student__last_name', 'exam__title']


class ExamPaperAdmin(admin.ModelAdmin):
    list_display = ['paper_code', 'exam', 'generated_at', 'is_used']
    list_filter = ['is_used', 'generated_at']
    search_fields = ['paper_code', 'exam__title']


class ScannedPaperAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'matched_exam', 'matched_student', 'ocr_student_id', 'uploaded_at']
    list_filter = ['status', 'processed', 'needs_review', 'uploaded_at']
    search_fields = ['ocr_student_id', 'matched_student__first_name']


class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ['scanned_paper', 'question', 'detected_answer', 'correct_answer',
                    'is_correct', 'is_blank', 'is_multiple_mark', 'question_points', 'earned_points', 'needs_review']
    list_filter = ['is_correct', 'is_blank', 'is_multiple_mark', 'needs_review']


class ExamResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'total_points', 'earned_points', 'score',
                    'correct_count', 'wrong_count', 'blank_count', 'multiple_mark_count',
                    'review_needed_count', 'needs_review', 'created_at']
    list_filter = ['exam', 'needs_review', 'created_at']
    search_fields = ['student__first_name', 'student__last_name', 'exam__title']


pink_admin_site = PinkAdminSite(name='pink_admin')

class AnswerKeyAdmin(admin.ModelAdmin):
    list_display = ['exam', 'uploaded_at', 'processed']
    list_filter = ['processed', 'uploaded_at']


pink_admin_site.register(Student, StudentAdmin)
pink_admin_site.register(Course, CourseAdmin)
pink_admin_site.register(Enrollment, EnrollmentAdmin)
pink_admin_site.register(Exam, ExamAdmin)
pink_admin_site.register(Question, QuestionAdmin)
pink_admin_site.register(AnswerKey, AnswerKeyAdmin)
pink_admin_site.register(ExamEnrollment, ExamEnrollmentAdmin)
pink_admin_site.register(ExamPaper, ExamPaperAdmin)
pink_admin_site.register(ScannedPaper, ScannedPaperAdmin)
pink_admin_site.register(StudentAnswer, StudentAnswerAdmin)
pink_admin_site.register(ExamResult, ExamResultAdmin)
