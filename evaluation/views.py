import json
import os
import random
import string
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from .models import (
    Student, Course, Enrollment, Exam, Question,
    ExamPaper, ScannedPaper, StudentAnswer, ExamResult,
    AnswerKey, University
)
from .permissions import is_admin, is_instructor, instructor_required
from .utils import qr_generator, ocr as ocr_utils, omr as omr_utils
from .utils.pipeline import process_scanned_paper as run_pipeline, grade_answers
from .utils.paper_generator import generate_exam_image


def get_user_role(user):
    if not user.is_authenticated:
        return 'anonymous'
    if user.is_superuser:
        return 'admin'
    if user.is_staff:
        return 'instructor'
    return 'user'


def generate_paper_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def ensure_exam_paper(exam):
    """Create or refresh the single shared PNG answer sheet for an exam."""
    from django.conf import settings

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'qr_codes'), exist_ok=True)
    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'exam_papers'), exist_ok=True)

    exam_paper, created = ExamPaper.objects.get_or_create(
        exam=exam,
        defaults={'paper_code': generate_paper_code()},
    )

    exam_paper.qr_image.save(
        f'qr_{exam_paper.paper_code}.png',
        qr_generator.generate_qr_image(exam),
        save=True,
    )

    png_buffer = generate_exam_image(exam, exam_paper, dpi=300)
    exam_paper.image_file.save(
        f'paper_{exam_paper.paper_code}.png',
        ContentFile(png_buffer.getvalue()),
        save=True,
    )
    return exam_paper, created


# ==================== INDEX ====================

@login_required
def index(request):
    user_role = get_user_role(request.user)
    if is_instructor(request.user):
        pending = ScannedPaper.objects.filter(status='needs_review',
            matched_exam__course__teacher=request.user).count()
    else:
        pending = ScannedPaper.objects.filter(status='needs_review').count()
    return render(request, 'index.html', {
        'pending_review': pending, 'user_role': user_role,
        'nav_active': 'dashboard',
    })


# ==================== STUDENTS ====================

@login_required
def student_list(request):
    return render(request, 'student_list.html', {
        'students': Student.objects.all(),
        'user_role': get_user_role(request.user),
        'nav_active': 'students',
    })


@login_required
def student_delete(request, student_id):
    if get_user_role(request.user) not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to delete students.")
    get_object_or_404(Student, id=student_id).delete()
    return redirect('student_list')


@login_required
def student_create(request):
    if get_user_role(request.user) not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to create students.")
    if request.method == 'POST':
        Student.objects.create(
            student_id=request.POST.get('student_id'),
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
            email=request.POST.get('email')
        )
        return redirect('student_list')
    return render(request, 'student_form.html', {
        'user_role': get_user_role(request.user), 'nav_active': 'students',
    })


# ==================== UNIVERSITIES ====================

@login_required
def university_list(request):
    universities = University.objects.all()
    return render(request, 'university_list.html', {
        'universities': universities, 'user_role': get_user_role(request.user), 'nav_active': 'universities',
    })

@login_required
def university_delete(request, uni_id):
    if get_user_role(request.user) not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to delete universities.")
    get_object_or_404(University, id=uni_id).delete()
    return redirect('university_list')

@login_required
def university_create(request):
    if get_user_role(request.user) not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to create universities.")
    if request.method == 'POST':
        name = request.POST.get('name')
        logo = request.FILES.get('logo')
        try:
            University.objects.create(name=name, logo=logo)
            return redirect('university_list')
        except Exception as e:
            return render(request, 'university_form.html', {
                'error': str(e), 'user_role': get_user_role(request.user), 'nav_active': 'universities',
            })
    return render(request, 'university_form.html', {
        'user_role': get_user_role(request.user), 'nav_active': 'universities',
    })


# ==================== COURSES ====================

@login_required
def course_list(request):
    courses = Course.objects.filter(teacher=request.user) if is_instructor(request.user) else Course.objects.all()
    return render(request, 'course_list.html', {
        'courses': courses, 'user_role': get_user_role(request.user), 'nav_active': 'courses',
    })


@login_required
def course_delete(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if is_instructor(request.user) and course.teacher != request.user:
        raise PermissionDenied("You can only delete your own courses.")
    course.delete()
    return redirect('course_list')


@login_required
@instructor_required
def course_create(request):
    universities = University.objects.all()
    if request.method == 'POST':
        uni_id = request.POST.get('university_id')
        uni = University.objects.filter(id=uni_id).first() if uni_id else None
        try:
            Course.objects.create(
                code=request.POST.get('code'), name=request.POST.get('name'),
                university=uni,
                credit=request.POST.get('credit', 3),
                ects=request.POST.get('ects', 3),
                instructor=request.POST.get('instructor', ''),
                teacher=request.user if is_instructor(request.user) else None,
            )
            return redirect('course_list')
        except Exception as e:
            return render(request, 'course_form.html', {
                'error': str(e), 'universities': universities, 'user_role': get_user_role(request.user), 'nav_active': 'courses',
            })
    return render(request, 'course_form.html', {
        'universities': universities, 'user_role': get_user_role(request.user), 'nav_active': 'courses',
    })


# ==================== ENROLLMENT ====================

@login_required
def enroll_student(request):
    if request.method == 'POST':
        student = get_object_or_404(Student, id=request.POST.get('student_id'))
        course = get_object_or_404(Course, id=request.POST.get('course_id'))
        Enrollment.objects.get_or_create(student=student, course=course, defaults={'is_active': True})
        messages.success(
            request,
            f'{student.full_name} enrolled in {course.code}. They can now take all exams for this course.',
        )
        return redirect('index')
    students = Student.objects.all()
    courses = Course.objects.filter(teacher=request.user) if is_instructor(request.user) else Course.objects.all()
    preselected_course_id = request.GET.get('course_id')
    if preselected_course_id:
        try:
            preselected_course_id = int(preselected_course_id)
        except (ValueError, TypeError):
            preselected_course_id = None
    return render(request, 'enroll_form.html', {
        'students': students, 'courses': courses,
        'user_role': get_user_role(request.user), 'nav_active': 'enrollment',
        'preselected_course_id': preselected_course_id,
    })


# ==================== EXAM ENROLLMENT ====================

@login_required
def enroll_student_exam(request):
    """Legacy URL — course enrollment covers all exams in a course."""
    exam_id = request.GET.get('exam_id') or request.POST.get('exam_id')
    if exam_id:
        exam = Exam.objects.filter(id=exam_id).select_related('course').first()
        if exam:
            if is_instructor(request.user) and exam.course.teacher != request.user:
                raise PermissionDenied("You can only enroll students in your own courses.")
            from django.urls import reverse
            return redirect(f"{reverse('enroll_student')}?course_id={exam.course_id}")
    return redirect('enroll_student')


# ==================== EXAMS ====================

@login_required
def exam_list(request):
    exams = Exam.objects.filter(course__teacher=request.user) if is_instructor(request.user) else Exam.objects.all()
    exams = exams.select_related('course').prefetch_related('questions')
    exam_rows = []
    for exam in exams:
        course_enrolled = Enrollment.objects.filter(course=exam.course, is_active=True).count()
        exam_rows.append({
            'exam': exam,
            'enrolled_count': course_enrolled,
            'result_count': ExamResult.objects.filter(exam=exam).count(),
            'has_paper': ExamPaper.objects.filter(exam=exam).exists(),
        })
    return render(request, 'exam_list.html', {
        'exam_rows': exam_rows,
        'user_role': get_user_role(request.user),
        'nav_active': 'exams',
    })


@login_required
def exam_manage(request, exam_id):
    exam = get_object_or_404(Exam.objects.select_related('course'), id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only manage your own exams.")

    course_enrolled = Enrollment.objects.filter(
        course=exam.course, is_active=True,
    ).select_related('student').order_by('student__last_name', 'student__first_name')

    paper = ExamPaper.objects.filter(exam=exam).first()
    result_count = ExamResult.objects.filter(exam=exam).count()

    return render(request, 'exam_manage.html', {
        'exam': exam,
        'course_enrolled': course_enrolled,
        'paper': paper,
        'result_count': result_count,
        'question_count': exam.questions.count(),
        'answer_key_configured': exam.is_answer_key_configured(),
        'user_role': get_user_role(request.user),
        'nav_active': 'exams',
    })


@login_required
def exam_delete(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only delete exams from your own courses.")
    exam.delete()
    return redirect('exam_list')


@login_required
@instructor_required
def exam_create(request):
    if request.method == 'POST':
        from datetime import datetime

        title = request.POST.get('title')
        course_id = request.POST.get('course_id')
        exam_date_raw = request.POST.get('exam_date')
        try:
            exam_date = datetime.strptime(exam_date_raw, '%Y-%m-%d').date() if exam_date_raw else None
        except (TypeError, ValueError):
            courses = Course.objects.filter(teacher=request.user) if is_instructor(request.user) else Course.objects.all()
            return render(request, 'exam_form.html', {
                'courses': courses,
                'user_role': get_user_role(request.user),
                'nav_active': 'exams',
                'error': 'Please enter a valid exam date.',
            })
        try:
            duration = int(request.POST.get('duration_minutes', 60) or 60)
        except (TypeError, ValueError):
            duration = 60

        try:
            omr_count = max(0, int(request.POST.get('omr_count', 5)))
            classical_count = max(0, int(request.POST.get('classical_count', 5)))
        except (TypeError, ValueError):
            omr_count, classical_count = 5, 5

        if omr_count + classical_count < 1:
            courses = Course.objects.filter(teacher=request.user) if is_instructor(request.user) else Course.objects.all()
            return render(request, 'exam_form.html', {
                'courses': courses,
                'user_role': get_user_role(request.user),
                'nav_active': 'exams',
                'error': 'Add at least one optical or classical question.',
            })

        course = get_object_or_404(Course, id=course_id)
        if is_instructor(request.user) and course.teacher != request.user:
            raise PermissionDenied("You can only create exams for your own courses.")

        rules = request.POST.get('rules', '').strip()

        exam = Exam.objects.create(
            title=title, course=course, exam_date=exam_date, duration_minutes=duration, rules=rules
        )

        qnum = 1
        for _ in range(omr_count):
            pts = request.POST.get(f'omr_points_{qnum}', '10')
            try:
                pts = float(pts)
            except ValueError:
                pts = 10.0
            correct = request.POST.get(f'omr_correct_{qnum}', '').strip().upper()
            if correct not in ('A', 'B', 'C', 'D', 'E'):
                correct = ''
            Question.objects.create(
                exam=exam,
                question_number=qnum,
                question_type=Question.TYPE_OMR,
                text='',
                correct_answer=correct,
                points=pts,
            )
            qnum += 1

        for _ in range(classical_count):
            pts = request.POST.get(f'classical_points_{qnum}', '10')
            try:
                pts = float(pts)
            except ValueError:
                pts = 10.0
            Question.objects.create(
                exam=exam,
                question_number=qnum,
                question_type=Question.TYPE_CLASSICAL,
                text='',
                correct_answer='',
                points=pts,
            )
            qnum += 1

        exam.refresh_sheet_layout()
        ensure_exam_paper(exam)
        return redirect('configure_exam', exam_id=exam.id)

    courses = Course.objects.filter(teacher=request.user) if is_instructor(request.user) else Course.objects.all()
    universities = University.objects.all()
    return render(request, 'exam_form.html', {
        'courses': courses, 'universities': universities, 'user_role': get_user_role(request.user), 'nav_active': 'exams',
    })


# ==================== ANSWER KEY CONFIGURATION ====================

@login_required
def configure_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only configure your own exams.")

    if request.method == 'POST':
        for question in exam.questions.all():
            pts = request.POST.get(f'points_{question.question_number}', str(question.points)).strip()
            try:
                pts = float(pts)
            except ValueError:
                pts = float(question.points)

            if question.is_omr:
                correct = request.POST.get(f'correct_{question.question_number}', '').strip().upper()
                question.correct_answer = correct if correct in ('A', 'B', 'C', 'D', 'E') else ''
            question.points = pts
            question.save(update_fields=['correct_answer', 'points'])

        if 'rules' in request.POST:
            exam.rules = request.POST.get('rules', '').strip()
            exam.save(update_fields=['rules'])

        exam.refresh_sheet_layout()
        ensure_exam_paper(exam)
        regraded = regrade_exam_results(exam)
        msg = 'Answer key saved. You can generate the paper or upload scans from the exam hub.'
        if regraded:
            msg += f' Re-graded {regraded} existing result(s).'
        messages.success(request, msg)
        return redirect('exam_manage', exam_id=exam.id)

    questions = exam.questions.all().order_by('question_number')
    omr_questions = [q for q in questions if q.is_omr]
    classical_questions = [q for q in questions if q.is_classical]
    configured = all(q.correct_answer in ('A', 'B', 'C', 'D', 'E') for q in omr_questions) if omr_questions else True
    return render(request, 'configure_exam.html', {
        'exam': exam,
        'questions': questions,
        'omr_questions': omr_questions,
        'classical_questions': classical_questions,
        'configured': configured,
        'user_role': get_user_role(request.user),
        'nav_active': 'exams',
    })


# ==================== EXAM PAPER GENERATION ====================

@login_required
def generate_exam_papers(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only generate papers for your own exams.")

    exam.refresh_sheet_layout()
    exam_paper, created = ensure_exam_paper(exam)

    return render(request, 'exam_generate_papers.html', {
        'exam': exam,
        'exam_paper': exam_paper,
        'paper_created': created,
        'user_role': get_user_role(request.user),
        'nav_active': 'exams',
    })


@login_required
def view_exam_paper(request, paper_id):
    """Download the exam answer sheet."""
    exam_paper = get_object_or_404(ExamPaper, id=paper_id)
    fmt = request.GET.get('format', 'png').lower()

    if fmt == 'pdf':
        if exam_paper.pdf_file:
            return FileResponse(exam_paper.pdf_file.open('rb'), content_type='application/pdf')
        else:
            from .utils.paper_generator import generate_exam_pdf
            pdf_buf = generate_exam_pdf(exam_paper.exam, exam_paper)
            return FileResponse(pdf_buf, content_type='application/pdf', filename=f'paper_{exam_paper.paper_code}.pdf')
            
    elif fmt == 'docx':
        from .utils.paper_generator import generate_exam_docx
        docx_buf = generate_exam_docx(exam_paper.exam, exam_paper)
        return FileResponse(
            docx_buf, 
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
            filename=f'paper_{exam_paper.paper_code}.docx'
        )

    else:
        if exam_paper.image_file:
            return FileResponse(
                exam_paper.image_file.open('rb'),
                content_type='image/png',
                filename=f'paper_{exam_paper.paper_code}.png',
            )

    return redirect('exam_list')


@login_required
def paper_detail(request, paper_id):
    """Show exam paper detail page with QR code."""
    exam_paper = get_object_or_404(ExamPaper, id=paper_id)
    questions = exam_paper.exam.questions.all()
    return render(request, 'exam_paper.html', {
        'exam_paper': exam_paper,
        'exam': exam_paper.exam,
        'questions': questions,
        'user_role': get_user_role(request.user),
    })


# ==================== UPLOAD & PROCESS ====================

@login_required
def upload_scanned_paper(request):
    user_role = get_user_role(request.user)

    if request.method == 'POST':
        image = request.FILES.get('image')
        if not image:
            return render(request, 'upload_scanned.html', {
                'error': 'Please select an image file.', 'user_role': user_role, 'nav_active': 'upload'
            })

        allowed = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']
        if image.name.split('.')[-1].lower() not in allowed:
            return render(request, 'upload_scanned.html', {
                'error': 'Invalid format. Allowed: JPG, PNG, GIF, BMP, WebP', 'user_role': user_role, 'nav_active': 'upload'
            })

        try:
            from PIL import Image as PILImage
            try:
                with PILImage.open(image) as img:
                    img.verify()
                image.seek(0)
            except Exception:
                return render(request, 'upload_scanned.html', {
                    'error': 'Uploaded file is not a valid image or is corrupted.',
                    'user_role': user_role, 'nav_active': 'upload'
                })

            # Ensure media/scanned_papers directory exists
            from django.conf import settings
            os.makedirs(os.path.join(settings.MEDIA_ROOT, 'scanned_papers'), exist_ok=True)

            scanned = ScannedPaper.objects.create(image=image, status='processing')

            from PIL import Image as PILImage
            with PILImage.open(scanned.image.path) as check_img:
                img_w, img_h = check_img.size
            low_res_warning = ''
            if max(img_w, img_h) < 1200:
                low_res_warning = (
                    f'Low resolution ({img_w}x{img_h}). For reliable QR/OCR/OMR, '
                    'scan at 300 DPI or photograph the full page at 2000+ pixels wide.'
                )

            from .utils.qr_reader import read_qr_from_image
            from .utils.matching import match_exam_from_qr

            qr_preview = read_qr_from_image(scanned.image.path)
            matched_exam = match_exam_from_qr(qr_preview)
            result = run_pipeline(scanned.image.path, exam=matched_exam)

            # Store QR data
            qr = result['qr']
            qr_dict_initial = {
                'student_id': str(qr.get('student_id', '')),
                'exam_id': int(qr.get('exam_id', 0)) if qr.get('exam_id') else None,
                'page': int(qr.get('page', 1)) if qr.get('page') else None,
                'raw': str(qr.get('raw', '')),
                'needs_review': bool(qr.get('needs_review', False)),
                'error': str(qr.get('error', '')) if qr.get('error') else None
            }
            scanned.qr_data = json.dumps(qr_dict_initial)
            scanned.qr_success = not qr_dict_initial['needs_review']
            scanned.qr_confidence = 80.0 if not qr_dict_initial['needs_review'] else 0.0

            # Store OCR result
            ocr = result['ocr']
            scanned.ocr_student_id = ocr.get('student_id', '')
            scanned.ocr_confidence = ocr.get('confidence', 0.0)

            # Store OMR result (MCQ bubbles Q1-Q5)
            omr = result['omr']
            scanned.omr_confidence = omr.get('confidence', 0.0)
            omr_answers = omr.get('answers', [])

            # Store OCR scores (classical questions Q6-Q10)
            ocr_scores = result.get('ocr_scores', {}).get('scores', [])

            # Combine all answers: MCQ + classical scores
            all_answers = []
            for ans in omr_answers:
                all_answers.append({
                    'question_number': ans['question_number'],
                    'detected': ans['detected'],
                    'is_blank': bool(ans['is_blank']),
                    'needs_review': bool(ans['needs_review']),
                    'darkness_values': [float(v) for v in ans.get('darkness_values', [])],
                    'section': ans['section'],
                    'question_type': ans['question_type'],
                })
                
            for s in ocr_scores:
                all_answers.append({
                    'question_number': s['question_number'],
                    'detected': str(s.get('detected_score', 0)),
                    'is_blank': bool(s.get('is_blank', True)),
                    'needs_review': bool(s.get('needs_review', False)),
                    'exceeds_max': bool(s.get('exceeds_max', False)),
                    'section': 'Classical',
                    'question_type': 'classical',
                })

            scanned.detected_answers = json.dumps(all_answers)
            scanned.needs_review = bool(result['needs_review']) or bool(low_res_warning)
            
            qr_dict = {
                'student_id': str(qr.get('student_id', '')),
                'exam_id': int(qr.get('exam_id', 0)) if qr.get('exam_id') else None,
                'page': int(qr.get('page', 1)) if qr.get('page') else None,
                'raw': str(qr.get('raw', '')),
                'needs_review': bool(qr.get('needs_review', False)),
                'error': str(qr.get('error', '')) if qr.get('error') else None
            }
            if low_res_warning and qr_dict.get('error'):
                qr_dict['error'] = f'{low_res_warning} {qr_dict["error"]}'
                scanned.qr_data = json.dumps(qr_dict)
            elif low_res_warning:
                qr_dict['error'] = low_res_warning
                scanned.qr_data = json.dumps(qr_dict)
            else:
                scanned.qr_data = json.dumps(qr_dict)

            from .utils.matching import (
                match_exam_from_qr, match_student_from_ocr, is_student_enrolled_for_exam,
                can_auto_finalize_scan, normalize_student_id,
            )

            scanned.matched_exam = match_exam_from_qr(qr)
            ocr_id = normalize_student_id(ocr.get('student_id', ''))
            scanned.ocr_student_id = ocr_id
            scanned.matched_student = result.get('matched_student') or match_student_from_ocr(ocr_id)

            if (
                scanned.matched_exam
                and scanned.matched_student
                and not is_student_enrolled_for_exam(scanned.matched_student, scanned.matched_exam)
            ):
                scanned.status = 'failed'
                scanned.processed = True
                scanned.needs_review = False
                scanned.save()
                return render(request, 'upload_scanned.html', {
                    'error': (
                        f'Rejected: {scanned.matched_student.full_name} '
                        f'({scanned.matched_student.student_id}) is not enrolled in '
                        f'{scanned.matched_exam.course.code} — {scanned.matched_exam.course.name}. '
                        'Only students enrolled in the course may submit this exam.'
                    ),
                    'user_role': user_role, 'nav_active': 'upload',
                })

            if not scanned.matched_student:
                scanned.needs_review = True

            result_obj = None
            if scanned.matched_exam:
                if not scanned.matched_exam.is_answer_key_configured():
                    scanned.needs_review = True
                grading = grade_answers(
                    omr_answers,
                    scanned.matched_exam,
                    scanned.ocr_student_id or 'UNKNOWN',
                    ocr_scores=ocr_scores,
                )
                if can_auto_finalize_scan(scanned):
                    result_obj = finalize_scanned_result(scanned, grading, all_answers)
                    scanned.processed = True
                    scanned.status = 'completed'
                    scanned.needs_review = False
                else:
                    if omr_answers or ocr_scores:
                        save_student_answers(scanned, all_answers)
                    scanned.processed = True
                    scanned.status = 'needs_review'
                    scanned.needs_review = True
            else:
                scanned.status = 'needs_review'
                scanned.needs_review = True
                scanned.processed = True

            scanned.save()

            if result_obj:
                messages.success(
                    request,
                    f'Result saved for {result_obj.student.full_name} — '
                    f'{result_obj.exam.title} ({result_obj.exam.course.code}): '
                    f'{result_obj.earned_points}/{result_obj.total_points} points.',
                )
                return redirect('result_detail', result_id=result_obj.id)

            try:
                result_obj = ExamResult.objects.get(scanned_paper=scanned)
                return redirect('result_detail', result_id=result_obj.id)
            except ExamResult.DoesNotExist:
                pass

            if scanned.matched_exam and not scanned.matched_student and ocr_id:
                messages.warning(
                    request,
                    f'OCR read student ID {ocr_id} but could not match a student. '
                    'Please review and assign the correct student manually.',
                )
            elif scanned.matched_exam and scanned.matched_student:
                messages.warning(
                    request,
                    f'Student {scanned.matched_student.full_name} detected. '
                    'Confirm the assignment and save the result in review.',
                )
            else:
                messages.info(request, 'Image processed. Review may be needed.')

            return redirect('review_scanned', scanned_id=scanned.id)

        except Exception as e:
            import traceback
            traceback.print_exc()
            if 'scanned' in locals():
                scanned.status = 'failed'
                scanned.save(update_fields=['status'])
            return render(request, 'upload_scanned.html', {
                'error': f'Processing error: {str(e)}', 'user_role': user_role, 'nav_active': 'upload'
            })

    return render(request, 'upload_scanned.html', {'user_role': user_role, 'nav_active': 'upload'})


# ==================== ANSWER KEY UPLOAD ====================

@login_required
def upload_answer_key(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    user_role = get_user_role(request.user)
    questions = exam.questions.all()

    if request.method == 'POST':
        image = request.FILES.get('image')
        if not image:
            return render(request, 'upload_answer_key.html', {
                'error': 'Please select an image file.', 'exam': exam,
                'questions': questions, 'user_role': user_role, 'nav_active': 'exams'
            })

        try:
            from PIL import Image as PILImage
            with PILImage.open(image) as img:
                img.verify()
            image.seek(0)
        except Exception:
            return render(request, 'upload_answer_key.html', {
                'error': 'File is not a valid image.', 'exam': exam,
                'questions': questions, 'user_role': user_role, 'nav_active': 'exams'
            })

        # Ensure media directory exists
        from django.conf import settings
        media_dir = os.path.join(settings.MEDIA_ROOT, 'answer_keys')
        os.makedirs(media_dir, exist_ok=True)

        ak = AnswerKey.objects.create(exam=exam, image=image)

        try:
            layout = exam.get_sheet_layout()
            omr_numbers = list(
                exam.omr_questions.order_by('question_number').values_list('question_number', flat=True)
            )
            omr_result = omr_utils.process_omr(
                ak.image.path, omr_question_numbers=omr_numbers, layout=layout,
            )
            detected_answers = omr_result.get('answers', [])

            ak.detected_answers = json.dumps(detected_answers)
            ak.processed = True
            ak.save()

            updated_count = 0
            for ans in detected_answers:
                q_num = ans.get('question_number')
                detected_ans = ans.get('detected', '').strip().upper()
                if detected_ans and detected_ans in ('A', 'B', 'C', 'D', 'E'):
                    updated = Question.objects.filter(
                        exam=exam, question_number=q_num, question_type=Question.TYPE_OMR,
                    ).update(correct_answer=detected_ans)
                    if updated:
                        updated_count += 1

            if updated_count:
                regrade_exam_results(exam)

            return render(request, 'upload_answer_key.html', {
                'success': f'Answer key processed. {updated_count} answers updated.',
                'exam': exam, 'questions': questions,
                'detected_answers': detected_answers,
                'user_role': user_role, 'nav_active': 'exams', 'key_image': ak
            })

        except Exception as e:
            error_msg = str(e)
            return render(request, 'upload_answer_key.html', {
                'error': f'Error processing answer key image: {error_msg}',
                'exam': exam, 'questions': questions, 'user_role': user_role, 'nav_active': 'exams'
            })

    return render(request, 'upload_answer_key.html', {
        'exam': exam, 'questions': questions, 'user_role': user_role, 'nav_active': 'exams'
    })


# ==================== CSV EXPORT ====================

@login_required
def export_results_csv(request, exam_id):
    import csv
    from django.http import HttpResponse

    exam = get_object_or_404(Exam, id=exam_id)
    results = ExamResult.objects.filter(exam=exam).select_related('student', 'scanned_paper')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{exam.title}_results.csv"'

    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Student Name', 'Correct', 'Wrong', 'Blank',
                     'Multiple Mark', 'Review Needed', 'Total Questions',
                     'Total Points', 'Earned Points', 'Score (%)'])

    for r in results.order_by('student__last_name', 'student__first_name', 'student__student_id'):
        writer.writerow([
            r.student.student_id, r.student.full_name,
            r.correct_count, r.wrong_count, r.blank_count,
            r.multiple_mark_count, r.review_needed_count,
            r.total_questions, r.total_points, r.earned_points, r.score
        ])

    return response


@login_required
def export_results_json(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only export results for your own exams.")

    results = ExamResult.objects.filter(exam=exam).select_related('student', 'scanned_paper').order_by(
        'student__last_name', 'student__first_name', 'student__student_id',
    )

    payload = {
        'exam': {
            'id': exam.id,
            'title': exam.title,
            'course_code': exam.course.code,
            'course_name': exam.course.name,
            'exam_date': str(exam.exam_date),
            'duration_minutes': exam.duration_minutes,
        },
        'results': [],
    }

    for result in results:
        payload['results'].append({
            'student_id': result.student.student_id,
            'student_name': result.student.full_name,
            'correct_count': result.correct_count,
            'wrong_count': result.wrong_count,
            'blank_count': result.blank_count,
            'multiple_mark_count': result.multiple_mark_count,
            'review_needed_count': result.review_needed_count,
            'total_questions': result.total_questions,
            'total_points': float(result.total_points),
            'earned_points': float(result.earned_points),
            'score_percent': float(result.score),
        })

    response = JsonResponse(payload, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="{exam.title}_results.json"'
    return response


# ==================== RESULTS ====================

@login_required
def results_list(request):
    """List all registered exams; open one to see its student results."""
    from django.db.models import Count

    exams = Exam.objects.filter(course__teacher=request.user) if is_instructor(request.user) else Exam.objects.all()
    exams = exams.select_related('course').annotate(result_count=Count('results')).order_by('-exam_date')

    exam_rows = []
    for exam in exams:
        exam_rows.append({
            'exam': exam,
            'result_count': exam.result_count,
            'enrolled_count': Enrollment.objects.filter(course=exam.course, is_active=True).count(),
        })

    if is_instructor(request.user):
        pending = ScannedPaper.objects.filter(
            status='needs_review', matched_exam__course__teacher=request.user,
        )
    else:
        pending = ScannedPaper.objects.filter(status='needs_review')

    return render(request, 'results_list.html', {
        'exam_rows': exam_rows,
        'pending': pending,
        'user_role': get_user_role(request.user),
        'nav_active': 'results',
    })


@login_required
def exam_results(request, exam_id):
    """Show all graded student results for one exam, in name order."""
    exam = get_object_or_404(Exam.objects.select_related('course'), id=exam_id)
    if is_instructor(request.user) and exam.course.teacher != request.user:
        raise PermissionDenied("You can only view results for your own exams.")

    results = (
        ExamResult.objects.filter(exam=exam)
        .select_related('student', 'scanned_paper')
        .order_by('student__last_name', 'student__first_name', 'student__student_id')
    )

    return render(request, 'exam_results.html', {
        'exam': exam,
        'results': results,
        'enrolled_count': Enrollment.objects.filter(course=exam.course, is_active=True).count(),
        'user_role': get_user_role(request.user),
        'nav_active': 'results',
    })


def _enrich_result_answers(result, answers):
    """Fill missing fields from scan detections and the live question bank."""
    questions = {
        q.question_number: q
        for q in result.exam.questions.all()
    }

    raw_by_q = {}
    if result.scanned_paper and result.scanned_paper.detected_answers:
        for item in json.loads(result.scanned_paper.detected_answers):
            raw_by_q[item.get('question_number')] = item

    enriched = []
    for ans in answers:
        item = dict(ans)
        q_num = item.get('question_number')
        question = questions.get(q_num)

        stored = str(item.get('detected', '') or '').strip()
        if stored.upper() in ('', 'BLANK') and q_num in raw_by_q:
            raw_value = str(raw_by_q[q_num].get('detected', '') or '').strip()
            if raw_value:
                item['detected'] = raw_value

        correct = str(item.get('correct_answer', '') or '').strip()
        if question:
            if question.is_omr and question.correct_answer:
                item['correct_answer'] = question.correct_answer
            elif question.is_classical and not correct:
                item['correct_answer'] = f'{float(question.points):g} pts max'
            elif question.is_omr and not correct:
                item['correct_answer'] = 'Not set'

        enriched.append(item)
    return enriched


def regrade_exam_results(exam):
    """Re-compute stored results after the answer key or points change."""
    count = 0
    results = ExamResult.objects.filter(exam=exam).select_related('scanned_paper', 'student')
    for result in results:
        scanned = result.scanned_paper
        if not scanned:
            continue
        grading, _ = grade_scanned_paper(scanned)
        if not grading:
            continue
        all_answers, _, _ = parse_scanned_answers(scanned)
        save_graded_result(scanned, grading)
        if all_answers:
            save_student_answers(scanned, all_answers)
        count += 1
    return count


@login_required
def result_detail(request, result_id):
    result = get_object_or_404(ExamResult, id=result_id)
    answers = _enrich_result_answers(result, result.get_answers())
    student_answers = StudentAnswer.objects.filter(scanned_paper=result.scanned_paper).select_related('question')
    return render(request, 'result_detail.html', {
        'result': result, 'answers': answers, 'student_answers': student_answers,
        'user_role': get_user_role(request.user), 'nav_active': 'results',
    })


@login_required
def result_delete(request, result_id):
    result = get_object_or_404(ExamResult, id=result_id)
    role = get_user_role(request.user)
    if role not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to delete results.")
    if role == 'instructor' and result.exam.course.teacher != request.user:
        raise PermissionDenied("You can only delete results from your own courses.")
    exam_id = result.exam_id
    result.delete()
    return redirect('exam_results', exam_id=exam_id)


# ==================== SCAN HISTORY ====================

@login_required
def scan_history(request):
    if is_instructor(request.user):
        scanned = ScannedPaper.objects.filter(matched_exam__course__teacher=request.user)
    else:
        scanned = ScannedPaper.objects.all()
    return render(request, 'scan_history.html', {
        'scanned': scanned, 'user_role': get_user_role(request.user), 'nav_active': 'scans',
    })


# ==================== MANUAL REVIEW ====================

@login_required
def pending_reviews(request):
    if is_instructor(request.user):
        pending = ScannedPaper.objects.filter(
            status='needs_review', matched_exam__course__teacher=request.user
        ).select_related('matched_exam', 'matched_student')
    else:
        pending = ScannedPaper.objects.filter(status='needs_review').select_related(
            'matched_exam', 'matched_student',
        )

    for scanned in pending:
        scanned.score_preview = None
        if scanned.matched_exam:
            grading, _ = grade_scanned_paper(scanned)
            scanned.score_preview = grading

    return render(request, 'pending_reviews.html', {
        'pending': pending,
        'user_role': get_user_role(request.user),
        'nav_active': 'reviews',
    })


@login_required
def review_scanned(request, scanned_id):
    """Review a scan, assign the student, preview scores, and save the result."""
    scanned = get_object_or_404(
        ScannedPaper.objects.select_related('matched_exam', 'matched_exam__course', 'matched_student'),
        id=scanned_id,
    )

    from .utils.matching import (
        match_exam_from_qr, match_student_from_ocr, is_student_enrolled_for_exam,
        can_auto_finalize_scan, normalize_student_id,
        refresh_student_match_from_scan, suggest_students_for_scan, get_enrolled_students,
    )

    if scanned.qr_data and not scanned.matched_exam:
        try:
            qr = json.loads(scanned.qr_data)
            scanned.matched_exam = match_exam_from_qr(qr)
            if scanned.matched_exam:
                scanned.save(update_fields=['matched_exam'])
        except Exception:
            pass

    matched_student, matched_id = refresh_student_match_from_scan(scanned)
    update_fields = []
    if matched_student and not scanned.matched_student:
        scanned.matched_student = matched_student
        update_fields.append('matched_student')
    if matched_id and matched_id != scanned.ocr_student_id:
        scanned.ocr_student_id = matched_id
        update_fields.append('ocr_student_id')
    if update_fields:
        scanned.save(update_fields=update_fields)

    if not scanned.matched_student and scanned.ocr_student_id:
        scanned.matched_student = match_student_from_ocr(scanned.ocr_student_id)
        if scanned.matched_student:
            scanned.save(update_fields=['matched_student'])

    grading, answer_details = grade_scanned_paper(scanned)
    all_answers, _, _ = parse_scanned_answers(scanned)
    error = None

    existing_result = scanned.get_result()
    if existing_result:
        return redirect('result_detail', result_id=existing_result.id)

    if request.method == 'GET' and can_auto_finalize_scan(scanned):
        result = finalize_scanned_result(scanned, grading, all_answers)
        if result:
            messages.success(
                request,
                f'Result saved for {result.student.full_name} — '
                f'{result.exam.title} ({result.exam.course.code}).',
            )
            return redirect('result_detail', result_id=result.id)

    course_students = Student.objects.none()
    suggested_students = []
    not_enrolled = False

    if scanned.matched_exam:
        course_students = get_enrolled_students(scanned.matched_exam).order_by('last_name', 'first_name')
        suggested_students = suggest_students_for_scan(scanned, limit=8)
        if scanned.matched_student and not is_student_enrolled_for_exam(scanned.matched_student, scanned.matched_exam):
            not_enrolled = True

    if request.method == 'POST':
        student_pk = request.POST.get('student_id')
        if student_pk and not scanned.matched_student:
            scanned.matched_student = get_object_or_404(Student, id=student_pk)
            scanned.save(update_fields=['matched_student'])
            grading, answer_details = grade_scanned_paper(scanned)
            all_answers, _, _ = parse_scanned_answers(scanned)

        if not scanned.matched_exam:
            error = 'Cannot save result: exam is not identified. Re-upload a sheet with a readable QR code.'
        elif not scanned.matched_student:
            error = 'Could not read a matching student ID from the sheet. Select an enrolled student to continue.'
        elif not is_student_enrolled_for_exam(scanned.matched_student, scanned.matched_exam):
            error = (
                f'{scanned.matched_student.full_name} ({scanned.matched_student.student_id}) '
                f'is not enrolled in {scanned.matched_exam.course.code}. '
                'Only enrolled students can take this exam.'
            )
        else:
            grading, answer_details = grade_scanned_paper(scanned)
            all_answers, _, _ = parse_scanned_answers(scanned)
            result = finalize_scanned_result(scanned, grading, all_answers)
            if result:
                messages.success(
                    request,
                    f'Result saved for {result.student.full_name} — '
                    f'{result.exam.title} ({result.exam.course.code}): '
                    f'{result.earned_points}/{result.total_points} points.',
                )
                return redirect('result_detail', result_id=result.id)
            error = 'Could not save the result. Please try again.'

    return render(request, 'review_scanned.html', {
        'scanned': scanned,
        'grading': grading,
        'answer_details': answer_details,
        'course_students': course_students,
        'suggested_students': suggested_students,
        'suggested_student_ids': [student.id for student in suggested_students],
        'not_enrolled': not_enrolled,
        'error': error,
        'auto_matched': can_auto_finalize_scan(scanned),
        'user_role': get_user_role(request.user),
        'nav_active': 'reviews',
    })


@login_required
def delete_scanned_paper(request, scanned_id):
    """Permanently delete a scanned paper and any linked result records."""
    if request.method != 'POST':
        return redirect('review_scanned', scanned_id=scanned_id)

    scanned = get_object_or_404(
        ScannedPaper.objects.select_related('matched_exam', 'matched_exam__course'),
        id=scanned_id,
    )
    role = get_user_role(request.user)
    if role not in ('admin', 'instructor'):
        raise PermissionDenied("You do not have permission to delete scans.")
    if role == 'instructor' and scanned.matched_exam and scanned.matched_exam.course.teacher != request.user:
        raise PermissionDenied("You can only delete scans from your own courses.")

    scanned.delete()
    messages.success(request, f'Scan #{scanned_id} has been deleted.')
    return redirect('pending_reviews')


@login_required
def approve_review(request, scanned_id):
    """Legacy approve URL — open the full review page."""
    return redirect('review_scanned', scanned_id=scanned_id)


# ==================== HELPERS ====================

def parse_scanned_answers(scanned):
    """Split stored JSON answers into OMR and classical score lists."""
    all_answers = json.loads(scanned.detected_answers) if scanned.detected_answers else []
    omr_answers = [
        a for a in all_answers
        if a.get('question_type') == 'omr' or a.get('section') in ('OMR', 'MCQ')
    ]
    ocr_scores = []
    for a in all_answers:
        if a.get('question_type') == 'classical' or a.get('section') == 'Classical':
            ocr_scores.append({
                'question_number': a['question_number'],
                'detected_score': int(a.get('detected', 0)) if str(a.get('detected', '')).isdigit() else 0,
                'is_blank': a.get('is_blank', True),
                'needs_review': a.get('needs_review', False),
                'exceeds_max': a.get('exceeds_max', False),
            })
    return all_answers, omr_answers, ocr_scores


def grade_scanned_paper(scanned):
    """Compute grading for a scanned paper without saving."""
    if not scanned.matched_exam:
        return None, []
    all_answers, omr_answers, ocr_scores = parse_scanned_answers(scanned)
    grading = grade_answers(
        omr_answers,
        scanned.matched_exam,
        scanned.ocr_student_id or 'UNKNOWN',
        ocr_scores=ocr_scores,
    )
    return grading, grading.get('answer_details', [])


def finalize_scanned_result(scanned, grading, all_answers):
    """Persist ExamResult and per-question StudentAnswer rows."""
    if not scanned.matched_exam or not scanned.matched_student:
        return None

    scanned.needs_review = False
    scanned.status = 'completed'
    scanned.save(update_fields=['needs_review', 'status'])

    result = save_graded_result(scanned, grading)
    if all_answers:
        save_student_answers(scanned, all_answers)
    return result


def make_json_safe(obj):
    import numpy as np
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_safe(v) for v in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return make_json_safe(obj.tolist())
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def save_graded_result(scanned, grading):
    """Create or update ExamResult from grading data."""
    if not scanned.matched_exam or not scanned.matched_student:
        return None

    exam = scanned.matched_exam
    student = scanned.matched_student
    defaults = {
        'scanned_paper': scanned,
        'correct_count': grading['correct_count'],
        'wrong_count': grading['wrong_count'],
        'blank_count': grading['blank_count'],
        'multiple_mark_count': grading.get('multiple_mark_count', 0),
        'review_needed_count': grading.get('review_needed_count', 0),
        'total_questions': grading['total_questions'],
        'total_points': grading.get('total_points', grading['total_questions']),
        'earned_points': grading.get('earned_points', grading['score']),
        'score': grading['score'],
        'answers': json.dumps(make_json_safe(grading['answer_details'])),
        'confidence': scanned.omr_confidence,
        'needs_review': scanned.needs_review,
    }

    with transaction.atomic():
        ExamResult.objects.filter(scanned_paper=scanned).exclude(
            exam=exam, student=student,
        ).delete()

        result, _ = ExamResult.objects.update_or_create(
            exam=exam,
            student=student,
            defaults=defaults,
        )
    return result


def save_student_answers(scanned, detected_answers):
    """Create individual StudentAnswer records for each question."""
    if not scanned.matched_exam:
        return

    grading = None
    try:
        grading = scanned.get_result()
    except Exception:
        pass

    for ans in detected_answers:
        q_num = ans.get('question_number')
        question = scanned.matched_exam.questions.filter(question_number=q_num).first()
        if not question:
            continue

        is_classical = (
            ans.get('question_type') == 'classical'
            or ans.get('section') == 'Classical'
            or (question and question.is_classical)
        )
        detected = ans.get('detected', '').strip().upper()
        is_blank = detected == '' or detected == 'BLANK'
        is_multiple = ans.get('needs_review', False)

        if is_classical:
            detected_score = int(detected) if detected.isdigit() else 0
            q_points = float(question.points)
            exceeds_max = ans.get('exceeds_max', False) or (
                not is_blank and detected_score > q_points
            )
            if exceeds_max:
                earned = 0.0
                is_correct = False
                is_multiple = True
            else:
                earned = min(detected_score, q_points) if not is_blank else 0.0
                is_correct = earned >= q_points
            correct_answer_display = f'{q_points:g} pts max'
        else:
            correct_key = (question.correct_answer or '').strip().upper()
            if not correct_key:
                earned = 0.0
                is_correct = False
                correct_answer_display = 'Not set'
                is_multiple = is_multiple or True
            else:
                earned = 0.0 if (is_blank or is_multiple or detected != correct_key) else float(question.points)
                is_correct = not is_blank and not is_multiple and detected == correct_key
                correct_answer_display = correct_key

        StudentAnswer.objects.update_or_create(
            scanned_paper=scanned,
            question=question,
            defaults={
                'detected_answer': detected if not is_blank else '',
                'correct_answer': correct_answer_display,
                'is_correct': is_correct,
                'is_blank': is_blank,
                'is_multiple_mark': is_multiple,
                'question_points': question.points,
                'earned_points': earned,
                'confidence': 80.0 if not is_blank else 0.0,
                'needs_review': is_multiple,
            }
        )
