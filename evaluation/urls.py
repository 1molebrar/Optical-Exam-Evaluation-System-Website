from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('students/', views.student_list, name='student_list'),
    path('students/create/', views.student_create, name='student_create'),
    path('students/delete/<int:student_id>/', views.student_delete, name='student_delete'),

    path('universities/', views.university_list, name='university_list'),
    path('universities/create/', views.university_create, name='university_create'),
    path('universities/delete/<int:uni_id>/', views.university_delete, name='university_delete'),

    path('courses/', views.course_list, name='course_list'),
    path('courses/create/', views.course_create, name='course_create'),
    path('courses/delete/<int:course_id>/', views.course_delete, name='course_delete'),

    path('enroll/', views.enroll_student, name='enroll_student'),
    path('exams/enroll/', views.enroll_student_exam, name='enroll_student_exam'),

    path('exams/', views.exam_list, name='exam_list'),
    path('exams/<int:exam_id>/manage/', views.exam_manage, name='exam_manage'),
    path('exams/create/', views.exam_create, name='exam_create'),
    path('exams/delete/<int:exam_id>/', views.exam_delete, name='exam_delete'),
    path('exams/<int:exam_id>/configure/', views.configure_exam, name='configure_exam'),
    path('exams/<int:exam_id>/generate/', views.generate_exam_papers, name='generate_exam_papers'),
    path('exams/<int:exam_id>/upload-answer-key/', views.upload_answer_key, name='upload_answer_key'),
    path('exam-paper/<int:paper_id>/', views.view_exam_paper, name='view_exam_paper'),
    path('exam-paper/<int:paper_id>/html/', views.paper_detail, name='paper_detail'),

    path('upload/', views.upload_scanned_paper, name='upload_scanned_paper'),
    path('scan-history/', views.scan_history, name='scan_history'),

    path('results/', views.results_list, name='results_list'),
    path('results/exam/<int:exam_id>/', views.exam_results, name='exam_results'),
    path('results/<int:result_id>/', views.result_detail, name='result_detail'),
    path('results/delete/<int:result_id>/', views.result_delete, name='result_delete'),
    path('results/export/<int:exam_id>/', views.export_results_csv, name='export_results_csv'),
    path('results/export/<int:exam_id>/json/', views.export_results_json, name='export_results_json'),

    path('reviews/', views.pending_reviews, name='pending_reviews'),
    path('reviews/<int:scanned_id>/', views.review_scanned, name='review_scanned'),
    path('reviews/<int:scanned_id>/delete/', views.delete_scanned_paper, name='delete_scanned_paper'),
    path('reviews/<int:scanned_id>/approve/', views.approve_review, name='approve_review'),
]
