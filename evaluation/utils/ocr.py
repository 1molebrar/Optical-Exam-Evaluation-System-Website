"""OCR for student ID from the new Topkapi template cell."""
import cv2
import pytesseract
from .image_prep import load_and_warp
from .paper_layout import DEFAULT_LAYOUT, get_student_id_box_rects
from .matching import normalize_student_id

ID_LENGTH = 11

def extract_student_id(image_path, warped_gray=None, layout=None, markers_found=None):
    """Extract the student ID from the top handwritten boxes."""
    from .digit_reader import read_single_digit_from_box
    
    print("OCR FUNCTION CALLED")
    layout = layout or DEFAULT_LAYOUT

    if warped_gray is None:
        prep = load_and_warp(image_path)
        if prep['warped'] is None:
            return {
                'student_id': '',
                'confidence': 0.0,
                'needs_review': True,
                'error': prep['error'] or 'Could not read image',
            }
        warped_gray = prep['warped']
        markers_found = prep['markers_found']
    elif markers_found is None:
        markers_found = True

    box_rects = get_student_id_box_rects(layout)
    student_id = ""
    confidences = []
    
    for (x1, y1, x2, y2) in box_rects:
        box_gray = warped_gray[y1:y2, x1:x2]
        digit, conf, is_blank = read_single_digit_from_box(box_gray)
        if not is_blank and digit:
            student_id += str(digit)
            confidences.append(conf)
        else:
            student_id += "?"
            confidences.append(0.0)

    needs_review = (
        not markers_found
        or "?" in student_id
        or len(student_id) != ID_LENGTH
    )
    
    student_id_clean = student_id.replace('?', '')
    
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    if not markers_found:
        avg_conf -= 20.0

    return {
        'student_id': student_id_clean,
        'confidence': round(max(0.0, avg_conf), 1),
        'needs_review': needs_review,
        'error': None,
        'digits': list(student_id_clean),
    }