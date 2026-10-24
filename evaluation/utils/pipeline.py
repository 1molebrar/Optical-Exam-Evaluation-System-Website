"""Evaluation Pipeline - orchestrates QR reading, OCR, OMR, grading."""
import os
from . import ocr as ocr_utils
from . import omr as omr_utils
from . import image_prep
from .qr_reader import read_qr_from_image

def validate_image(image_path):
    if not image_path or not os.path.exists(image_path):
        return False, 'Image file not found'
    from PIL import Image
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True, None
    except Exception as exc:
        return False, f'Invalid image: {exc}'

def _question_numbers(exam, question_type):
    return list(
        exam.questions.filter(question_type=question_type)
        .order_by('question_number')
        .values_list('question_number', flat=True)
    )

def process_scanned_paper(image_path, exam=None):
    """Complete processing pipeline for a scanned answer sheet."""
    valid, err = validate_image(image_path)
    if not valid:
        error_result = {
            'exam_id': None, 'course_code': None, 'needs_review': True, 'error': err,
        }
        return {
            'qr': error_result,
            'ocr': {'student_id': '', 'confidence': 0.0, 'needs_review': True, 'error': err},
            'omr': {'answers': [], 'needs_review': True, 'confidence': 0.0, 'error': err},
            'ocr_scores': {'scores': [], 'needs_review': True, 'error': err},
            'needs_review': True,
            'markers_found': False,
        }

    qr_result = read_qr_from_image(image_path)

    if exam is None and qr_result.get('exam_id'):
        from evaluation.models import Exam
        exam = Exam.objects.filter(id=qr_result['exam_id']).first()

    if exam is not None:
        exam.refresh_sheet_layout()

    layout = exam.get_sheet_layout() if exam else None
    if layout is None and qr_result.get('omr_count') is not None:
        from .layout_engine import compute_sheet_layout
        layout = compute_sheet_layout(
            qr_result.get('omr_count', 0),
            qr_result.get('classical_count', 4),
        )

    prep = image_prep.load_and_warp(image_path)
    warped = prep['warped']
    markers_found = prep['markers_found']

    if warped is None:
        err = prep['error'] or 'Could not process image'
        error_result = {'exam_id': None, 'course_code': None, 'needs_review': True, 'error': err}
        return {
            'qr': qr_result if qr_result.get('error') else error_result,
            'ocr': {'student_id': '', 'confidence': 0.0, 'needs_review': True, 'error': err},
            'omr': {'answers': [], 'needs_review': True, 'confidence': 0.0, 'error': err},
            'ocr_scores': {'scores': [], 'needs_review': True, 'error': err},
            'needs_review': True,
            'markers_found': False,
        }

    omr_numbers = _question_numbers(exam, 'omr') if exam else None
    classical_numbers = _question_numbers(exam, 'classical') if exam else None

    def try_extract_ids(test_layout):
        ocr_res = ocr_utils.extract_student_id(
            image_path, warped_gray=warped, layout=test_layout, markers_found=markers_found,
        )
        omr_res = omr_utils.process_student_id_omr(
            image_path, layout=test_layout, warped_gray=warped, markers_found=markers_found,
        )
        return ocr_res, omr_res

    ocr_result, omr_id_result = try_extract_ids(layout)

    # Legacy Layout Fallback (Check if student ID is empty or only '?')
    def has_valid_id(res):
        sid = res.get('student_id', '')
        return bool(sid.replace('?', '').strip())

    if not has_valid_id(ocr_result) and not has_valid_id(omr_id_result):
        legacy_layout = dict(layout)
        # Revert to the old column position (CONTENT_LEFT + INFO_COL_WIDTHS[0])
        legacy_layout['student_id_grid_x'] = legacy_layout.get('content_left', 42) + 204
        
        legacy_ocr, legacy_omr = try_extract_ids(legacy_layout)
        if has_valid_id(legacy_ocr) or has_valid_id(legacy_omr):
            ocr_result, omr_id_result = legacy_ocr, legacy_omr

    matched_student = None
    final_student_id = ""
    id_needs_review = True
    
    ocr_id = ocr_result.get('student_id', '')
    omr_id = omr_id_result.get('student_id', '')

    if exam and warped is not None and layout is not None:
        from .matching import match_student_from_id_boxes, normalize_student_id
        # match_student_from_id_boxes tries to fuzzy match. Since we have two sources now, 
        # we will use OMR as primary, and fallback to OCR.
        
        from evaluation.models import Student
        def find_student(sid):
            if not sid or "?" in sid: return None
            return Student.objects.filter(student_id=sid).first()
            
        student_omr = find_student(omr_id)
        student_ocr = find_student(ocr_id)
        
        if student_omr:
            matched_student = student_omr
            final_student_id = omr_id
            id_needs_review = False
        elif student_ocr:
            matched_student = student_ocr
            final_student_id = ocr_id
            id_needs_review = True # Flag review if we had to fall back to OCR
        else:
            final_student_id = omr_id if "?" not in omr_id else ocr_id
            id_needs_review = True

    # Store combined result back in ocr_result for the rest of pipeline compatibility
    ocr_result['student_id'] = final_student_id
    ocr_result['needs_review'] = id_needs_review
    ocr_result['omr_id'] = omr_id
    ocr_result['ocr_id'] = ocr_id

    omr_result = omr_utils.process_omr(
        image_path, omr_question_numbers=omr_numbers, layout=layout,
        warped_gray=warped, markers_found=markers_found,
    )
    classical_max_points = None
    if exam:
        classical_max_points = {
            q.question_number: float(q.points)
            for q in exam.questions.filter(question_type='classical')
        }

    ocr_scores_result = omr_utils.process_ocr_scores(
        image_path, classical_question_numbers=classical_numbers, layout=layout,
        warped_gray=warped, markers_found=markers_found,
        classical_max_points=classical_max_points,
    )

    if not markers_found:
        ocr_result['needs_review'] = True
        omr_result['needs_review'] = True
        ocr_scores_result['needs_review'] = True

    needs_review = (
        qr_result['needs_review']
        or ocr_result['needs_review']
        or omr_result['needs_review']
        or ocr_scores_result['needs_review']
        or not markers_found
    )

    return {
        'qr': qr_result,
        'ocr': ocr_result,
        'omr': omr_result,
        'ocr_scores': ocr_scores_result,
        'needs_review': needs_review,
        'markers_found': markers_found,
        'layout': layout,
        'matched_student': matched_student,
    }


def grade_answers(detected_answers, exam, student_id, ocr_scores=None):
    """Grade optical and classical questions using per-question points."""
    questions = {q.question_number: q for q in exam.questions.all()}
    answer_details = []
    correct = 0
    wrong = 0
    blank = 0
    multiple_mark = 0
    review_needed = 0
    total_points = 0
    earned_points = 0

    for ans in detected_answers:
        q_num = ans['question_number']
        question = questions.get(q_num)
        if not question or not question.is_omr:
            continue

        detected = ans.get('detected', '').strip().upper()
        is_multiple = ans.get('needs_review', False)
        correct_answer = (question.correct_answer or '').strip().upper()
        q_points = float(question.points)
        total_points += q_points

        if is_multiple:
            multiple_mark += 1
            review_needed += 1

        if not correct_answer:
            review_needed += 1
            if detected == '' or detected == 'BLANK':
                blank += 1
                final_answer = 'BLANK'
            else:
                final_answer = detected
            earned_points += 0.0
            answer_details.append({
                'question_number': q_num,
                'detected': final_answer,
                'correct_answer': 'Not set',
                'is_correct': False,
                'is_partial': False,
                'question_points': q_points,
                'earned_points': 0.0,
                'needs_review': True,
                'section': 'OMR',
                'question_type': 'omr',
            })
            continue

        if detected == '' or detected == 'BLANK':
            blank += 1
            is_correct = False
            final_answer = 'BLANK'
            earned = 0.0
        elif detected == correct_answer and not is_multiple:
            correct += 1
            is_correct = True
            final_answer = detected
            earned = q_points
        else:
            wrong += 1
            is_correct = False
            final_answer = detected
            earned = 0.0

        earned_points += earned
        answer_details.append({
            'question_number': q_num,
            'detected': final_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'is_partial': False,
            'question_points': q_points,
            'earned_points': earned,
            'needs_review': is_multiple,
            'section': 'OMR',
            'question_type': 'omr',
        })

    if ocr_scores:
        for score_item in ocr_scores:
            q_num = score_item['question_number']
            question = questions.get(q_num)
            if not question or not question.is_classical:
                continue

            detected_score = max(0, int(score_item.get('detected_score', 0) or 0))
            is_blank = score_item.get('is_blank', True)
            score_needs_review = score_item.get('needs_review', False)
            exceeds_max = score_item.get('exceeds_max', False)
            q_points = float(question.points)
            total_points += q_points

            is_partial = False
            if is_blank:
                blank += 1
                final_answer = 'BLANK'
                earned = 0.0
                is_correct = False
            elif exceeds_max:
                review_needed += 1
                wrong += 1
                final_answer = str(detected_score)
                earned = 0.0
                is_correct = False
                score_needs_review = True
            else:
                if score_needs_review:
                    review_needed += 1
                final_answer = str(detected_score)
                earned = min(float(detected_score), q_points)
                is_full = earned >= q_points
                is_partial = 0 < earned < q_points
                is_correct = is_full
                if is_full or is_partial:
                    correct += 1
                else:
                    wrong += 1

            earned_points += earned
            answer_details.append({
                'question_number': q_num,
                'detected': final_answer,
                'correct_answer': f'{q_points:g} pts max',
                'is_correct': is_correct,
                'is_partial': bool(is_partial if not is_blank and not exceeds_max else False),
                'exceeds_max': bool(exceeds_max),
                'question_points': q_points,
                'earned_points': earned,
                'needs_review': score_needs_review,
                'section': 'Classical',
                'question_type': 'classical',
            })

    answer_details.sort(key=lambda item: item['question_number'])
    total = len(answer_details)
    score = round((earned_points / total_points * 100), 2) if total_points > 0 else 0

    return {
        'student_id': student_id,
        'correct_count': correct,
        'wrong_count': wrong,
        'blank_count': blank,
        'multiple_mark_count': multiple_mark,
        'review_needed_count': review_needed,
        'total_questions': total,
        'total_points': round(total_points, 2),
        'earned_points': round(earned_points, 2),
        'score': score,
        'answer_details': answer_details,
    }
