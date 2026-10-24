"""Exam and student matching from QR/OCR scan results."""
import re

from evaluation.models import Exam, Student, Enrollment


def normalize_student_id(raw):
    """Keep only digits from an OCR-read school number."""
    if not raw:
        return ''
    return re.sub(r'[^0-9]', '', str(raw))


def get_enrolled_students(exam):
    """Return students enrolled in the exam's course."""
    if not exam:
        return Student.objects.none()

    course_ids = Enrollment.objects.filter(
        course=exam.course, is_active=True,
    ).values_list('student_id', flat=True)
    return Student.objects.filter(id__in=course_ids).order_by('student_id')


def match_exam_from_qr(qr):
    """Match an exam from decoded QR data."""
    if not qr:
        return None

    exam_id = qr.get('exam_id')
    if exam_id:
        exam = Exam.objects.filter(id=exam_id).first()
        if exam:
            return exam

    course_code = qr.get('course_code')
    if course_code:
        return Exam.objects.filter(course__code=course_code).order_by('-exam_date').first()

    return None


def match_student_from_qr(qr, ocr_student_id=''):
    """Match student from paper-code fallback or OCR school number."""
    if qr and qr.get('student_id'):
        student = Student.objects.filter(student_id=qr['student_id']).first()
        if student:
            return student

    return match_student_from_ocr(ocr_student_id)


def match_student_from_ocr(student_id_raw):
    """Match a student from OCR-read school number (exact match on digits)."""
    normalized = normalize_student_id(student_id_raw)
    if len(normalized) < 8:
        return None

    student = Student.objects.filter(student_id=normalized).first()
    if student:
        return student

    stripped = normalized.lstrip('0') or '0'
    if stripped != normalized:
        return Student.objects.filter(student_id=stripped).first()

    return None


def _get_id_box_rects(warped_gray, layout):
    from .alignment_refine import refine_student_id_box_rects
    from .paper_layout import get_student_id_box_rects

    if warped_gray is None:
        return get_student_id_box_rects(layout)
    return refine_student_id_box_rects(warped_gray, layout)


def _read_id_box_data(warped_gray, layout, box_rects=None):
    """Read per-box digit candidates and naive OCR digits from aligned scan."""
    from .digit_reader import read_id_box_candidates, read_single_digit_from_box

    if box_rects is None:
        box_rects = _get_id_box_rects(warped_gray, layout)

    box_candidates = []
    naive_digits = []
    for x1, y1, x2, y2 in box_rects:
        pad = 1
        box = warped_gray[
            max(0, y1 - pad):min(warped_gray.shape[0], y2 + pad),
            max(0, x1 - pad):min(warped_gray.shape[1], x2 + pad),
        ]
        box_candidates.append(read_id_box_candidates(box))
        digit, _, blank = read_single_digit_from_box(box)
        naive_digits.append('' if blank else digit)

    return box_candidates, normalize_student_id(''.join(naive_digits))


def _score_student_against_id_boxes(student, box_candidates):
    """Score how well a student's ID fits the digit-box candidates."""
    sid = normalize_student_id(student.student_id)
    if len(sid) != 11:
        return -999.0, sid

    score = 0.0
    strong_matches = 0
    for idx, candidates in enumerate(box_candidates):
        if idx >= len(sid):
            break
        expected = sid[idx]
        if not candidates:
            score -= 5.0
            continue

        best_digit, best_score = candidates[0]
        position_score = max((c for d, c in candidates if d == expected), default=0.0)
        if position_score >= 3.5:
            score += position_score
            if best_digit == expected and best_score >= 4.0:
                strong_matches += 1
            elif position_score >= 4.5:
                strong_matches += 1
        elif best_digit == expected:
            score += max(position_score, 2.0)
        else:
            score -= 4.0

    score += strong_matches * 0.75
    return score, sid


def rank_students_from_id_boxes(warped_gray, layout, students, limit=8):
    """Return students ranked by ID-box match score (best first)."""
    if warped_gray is None or layout is None:
        return []

    box_candidates, _ = _read_id_box_data(warped_gray, layout)
    ranked = []
    for student in students:
        score, sid = _score_student_against_id_boxes(student, box_candidates)
        if score > -999.0:
            ranked.append((score, student, sid))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]


def _count_strong_id_positions(student, box_candidates):
    """Count ID boxes where the student's digit is the top candidate."""
    sid = normalize_student_id(student.student_id)
    matches = 0
    for idx, candidates in enumerate(box_candidates):
        if idx >= len(sid) or not candidates:
            continue
        if candidates[0][0] == sid[idx]:
            matches += 1
    return matches


def match_student_from_id_boxes(warped_gray, layout, exam):
    """Match a student by scoring ID-box digits against course-enrolled students."""
    if warped_gray is None or exam is None:
        return None, ''

    box_candidates, naive_id = _read_id_box_data(warped_gray, layout)
    enrolled = list(get_enrolled_students(exam))

    exact = match_student_from_ocr(naive_id)
    if exact and len(naive_id) == 11:
        if not enrolled or exact in enrolled:
            return exact, naive_id

    ranked = []
    for student in enrolled:
        score, sid = _score_student_against_id_boxes(student, box_candidates)
        if score > -999.0:
            ranked.append((score, student, sid, _count_strong_id_positions(student, box_candidates)))

    ranked.sort(key=lambda item: (item[0], item[3]), reverse=True)
    if not ranked:
        if exact and len(naive_id) == 11:
            return exact, naive_id
        return None, naive_id

    best_score, best_student, best_id, best_positions = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else -999.0
    margin = best_score - second_score

    if exact and len(naive_id) == 11:
        if not enrolled or exact in enrolled:
            return exact, naive_id

    if (
        best_student
        and best_score >= 32.0
        and margin >= 6.0
        and best_positions >= 8
        and normalize_student_id(best_student.student_id) == best_id
    ):
        return best_student, best_id

    if (
        best_student
        and best_score >= 38.0
        and margin >= 14.0
        and normalize_student_id(best_student.student_id) == best_id
    ):
        return best_student, best_id

    if (
        best_student
        and best_score >= 28.0
        and margin >= 8.0
        and best_positions >= 7
        and len(naive_id) == 11
        and normalize_student_id(best_student.student_id) == naive_id
    ):
        return best_student, naive_id

    return None, naive_id


def suggest_students_for_scan(scanned, limit=8):
    """Suggest likely students for manual review from stored scan image."""
    if not scanned.matched_exam or not scanned.image:
        return []

    from . import image_prep
    from .layout_engine import layout_for_exam

    prep = image_prep.load_and_warp(scanned.image.path)
    layout = layout_for_exam(scanned.matched_exam)
    if prep['warped'] is None or layout is None:
        return []

    enrolled = list(get_enrolled_students(scanned.matched_exam))
    if enrolled:
        ranked = rank_students_from_id_boxes(prep['warped'], layout, enrolled, limit=limit)
    else:
        ranked = []

    return [student for score, student, sid in ranked if score >= 8.0]


def refresh_student_match_from_scan(scanned):
    """Re-read ID boxes from image and update student/OCR fields when confident."""
    if not scanned.matched_exam or not scanned.image:
        return None, normalize_student_id(scanned.ocr_student_id or '')

    from . import image_prep
    from .layout_engine import layout_for_exam

    prep = image_prep.load_and_warp(scanned.image.path)
    layout = layout_for_exam(scanned.matched_exam)
    if prep['warped'] is None or layout is None:
        return None, normalize_student_id(scanned.ocr_student_id or '')

    student, student_id = match_student_from_id_boxes(prep['warped'], layout, scanned.matched_exam)
    return student, student_id


def can_auto_finalize_scan(scanned):
    """True when exam + student are identified from the scan with no manual step."""
    if not scanned.matched_exam or not scanned.matched_student:
        return False
    if not is_student_enrolled_for_exam(scanned.matched_student, scanned.matched_exam):
        return False
    if not scanned.matched_exam.is_answer_key_configured():
        return False

    ocr_id = normalize_student_id(scanned.ocr_student_id)
    db_id = normalize_student_id(scanned.matched_student.student_id)
    return len(ocr_id) == 11 and ocr_id == db_id


def is_student_enrolled_for_exam(student, exam):
    """Return True if the student is enrolled in the exam's course."""
    if not student or not exam:
        return False

    return Enrollment.objects.filter(
        course=exam.course, student=student, is_active=True,
    ).exists()
