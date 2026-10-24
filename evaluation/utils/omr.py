"""OMR/OCR detection for optical bubbles and classical score boxes."""
import re
import cv2
import numpy as np

from .image_prep import load_and_warp
from .paper_layout import get_mcq_bubble_centers, get_classical_score_box_rects, get_student_id_bubble_centers, DEFAULT_LAYOUT
from .layout_engine import MCQ_OPTIONS
from .alignment_refine import refine_mcq_bubble_centers, refine_classical_score_box_rects

BUBBLE_FILLED_THRESHOLD = 150
BUBBLE_BLANK_THRESHOLD = 190
BUBBLE_SAMPLE_RADIUS = 9
MIN_ROW_CONTRAST = 22.0
MIN_FILL_MARGIN = 10.0

def sample_circle_darkness(gray, cx, cy, radius=BUBBLE_SAMPLE_RADIUS):
    h, w = gray.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (int(cx), int(cy)), radius, 255, -1)
    pixels = gray[mask == 255]
    if pixels.size == 0:
        return 255.0
    return float(np.mean(pixels))

def detect_answers_from_centers(row_centers, gray):
    darknesses = [sample_circle_darkness(gray, cx, cy) for cx, cy in row_centers]
    if len(darknesses) < len(MCQ_OPTIONS):
        return '', darknesses, True

    min_darkness = min(darknesses)
    sorted_dark = sorted(darknesses)
    second_dark = sorted_dark[1] if len(sorted_dark) > 1 else 255.0
    spread = second_dark - min_darkness
    median_dark = sorted_dark[len(sorted_dark) // 2]

    if spread < MIN_ROW_CONTRAST and min_darkness > BUBBLE_BLANK_THRESHOLD:
        return '', darknesses, False

    relative_filled = [
        idx for idx, value in enumerate(darknesses)
        if value < median_dark - 25 and value < BUBBLE_FILLED_THRESHOLD
    ]

    if not relative_filled:
        if min_darkness > BUBBLE_BLANK_THRESHOLD:
            return '', darknesses, False
        if spread < MIN_FILL_MARGIN:
            return '', darknesses, True
        detected_idx = darknesses.index(min_darkness)
        return MCQ_OPTIONS[detected_idx], darknesses, False

    if len(relative_filled) > 1:
        darkest_idx = min(relative_filled, key=lambda idx: darknesses[idx])
        next_dark = min(
            (darknesses[idx] for idx in relative_filled if idx != darkest_idx),
            default=255.0,
        )
        if darknesses[darkest_idx] + MIN_FILL_MARGIN <= next_dark:
            return MCQ_OPTIONS[darkest_idx], darknesses, False
        return '', darknesses, True

    detected_idx = relative_filled[0]
    return MCQ_OPTIONS[detected_idx], darknesses, False

def process_student_id_omr(image_path, layout=None, warped_gray=None, markers_found=None):
    layout = layout or DEFAULT_LAYOUT
    if warped_gray is None:
        prep = load_and_warp(image_path)
        if prep['warped'] is None:
            return {'student_id': '', 'needs_review': True, 'confidence': 0.0, 'error': prep['error']}
        warped_gray = prep['warped']
        markers_found = prep['markers_found']
    elif markers_found is None:
        markers_found = True

    bubble_centers = get_student_id_bubble_centers(layout)
    
    student_id = ""
    needs_review = not markers_found
    avg_conf = 100.0 if markers_found else 80.0
    
    for col_centers in bubble_centers:
        darknesses = [sample_circle_darkness(warped_gray, cx, cy, radius=4) for cx, cy in col_centers]
        min_darkness = min(darknesses)
        sorted_dark = sorted(darknesses)
        second_dark = sorted_dark[1] if len(sorted_dark) > 1 else 255.0
        spread = second_dark - min_darkness
        
        if min_darkness > BUBBLE_BLANK_THRESHOLD or spread < MIN_FILL_MARGIN:
            student_id += "?"
            needs_review = True
            avg_conf -= 10.0
        else:
            digit = darknesses.index(min_darkness)
            student_id += str(digit)
            
    if "?" in student_id:
        avg_conf = max(0.0, avg_conf - 40.0)

    return {
        'student_id': student_id,
        'needs_review': needs_review,
        'confidence': max(0.0, avg_conf),
        'error': None
    }

def _read_score_from_box(box_gray, max_value=100):
    from .digit_reader import read_number_from_box
    return read_number_from_box(box_gray, max_value=max_value)

def process_omr(image_path, omr_question_numbers=None, layout=None,
                warped_gray=None, markers_found=None):
    """Detect optical (MCQ) answers at template bubble positions."""
    layout = layout or DEFAULT_LAYOUT

    if warped_gray is None:
        prep = load_and_warp(image_path)
        if prep['warped'] is None:
            return {
                'answers': [], 'needs_review': True, 'confidence': 0.0,
                'error': prep['error'] or 'Could not read image',
            }
        warped_gray = prep['warped']
        markers_found = prep['markers_found']
    elif markers_found is None:
        markers_found = True

    if omr_question_numbers is None:
        omr_question_numbers = list(range(1, layout['omr_count'] + 1))

    bubble_centers = refine_mcq_bubble_centers(warped_gray, layout) if warped_gray is not None else get_mcq_bubble_centers(layout)
    answers = []
    needs_review = not markers_found
    confidence = 85.0 if markers_found else 50.0

    for idx, row_centers in enumerate(bubble_centers[:len(omr_question_numbers)]):
        q_num = omr_question_numbers[idx]
        detected, darknesses, review_flag = detect_answers_from_centers(row_centers, warped_gray)
        answers.append({
            'question_number': q_num,
            'detected': detected,
            'is_blank': detected == '',
            'needs_review': review_flag,
            'darkness_values': [round(value, 1) for value in darknesses],
            'section': 'OMR',
            'question_type': 'omr',
        })
        if review_flag:
            needs_review = True

    if any(answer['is_blank'] for answer in answers):
        confidence = max(confidence - 15, 10)
    if needs_review and confidence > 50:
        confidence = 50.0

    return {
        'answers': answers,
        'needs_review': needs_review,
        'confidence': round(confidence, 1),
        'error': None,
    }


def process_ocr_scores(image_path, classical_question_numbers=None, layout=None,
                       warped_gray=None, markers_found=None, classical_max_points=None):
    """Detect classical scores from template score boxes."""
    layout = layout or DEFAULT_LAYOUT

    if warped_gray is None:
        prep = load_and_warp(image_path)
        if prep['warped'] is None:
            return {'scores': [], 'needs_review': True, 'error': prep['error'] or 'Could not read image'}
        warped_gray = prep['warped']
        markers_found = prep['markers_found']
    elif markers_found is None:
        markers_found = True

    if classical_question_numbers is None:
        start = layout['omr_count'] + 1
        classical_question_numbers = list(range(start, start + layout['classical_count']))

    box_rects = (
        refine_classical_score_box_rects(warped_gray, layout)
        if warped_gray is not None
        else get_classical_score_box_rects(layout)
    )
    result = []
    needs_review = not markers_found

    for i, (x1, y1, x2, y2) in enumerate(box_rects[:len(classical_question_numbers)]):
        q_num = classical_question_numbers[i]
        # Sola kaydırmayı siliyoruz çünkü artık mükemmel kırpma (fiducial markers) yapıyoruz.
        box = warped_gray[y1:y2, x1:x2]
        score, conf, is_blank = _read_score_from_box(box)
        max_points = None
        if classical_max_points:
            max_points = classical_max_points.get(str(q_num))
        exceeds_max = (
            not is_blank
            and max_points is not None
            and score > float(max_points)
        )
        item_needs_review = bool(
            exceeds_max
            or (is_blank and conf < 80)
            or (not is_blank and conf < 85)
        )
        if not markers_found and is_blank:
            item_needs_review = True
        result.append({
            'question_number': q_num,
            'detected_score': score,
            'is_blank': bool(is_blank),
            'confidence': conf,
            'needs_review': bool(item_needs_review),
            'exceeds_max': bool(exceeds_max),
            'max_points': float(max_points) if max_points is not None else None,
        })
        if item_needs_review:
            needs_review = True

    return {'scores': result, 'needs_review': needs_review, 'error': None}
