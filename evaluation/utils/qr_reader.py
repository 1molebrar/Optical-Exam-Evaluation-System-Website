"""Robust QR code and Barcode reading with paper-code OCR fallback."""
import json
import re
import cv2
import numpy as np

def _empty_qr_result(error):
    return {
        'exam_id': None,
        'course_code': None,
        'exam_title': None,
        'course_name': None,
        'omr_count': None,
        'classical_count': None,
        'paper_code': None,
        'needs_review': True,
        'error': error,
        'source': None,
    }

def _parse_qr_payload(data):
    try:
        qr_info = json.loads(data)
    except json.JSONDecodeError:
        return _empty_qr_result(f'Invalid QR JSON: {data[:80]}')

    exam_id = qr_info.get('exam_id')
    if exam_id is None:
        return {
            'exam_id': None,
            'course_code': qr_info.get('course_code'),
            'exam_title': qr_info.get('exam_title'),
            'course_name': qr_info.get('course_name'),
            'omr_count': qr_info.get('omr_count'),
            'classical_count': qr_info.get('classical_count'),
            'paper_code': qr_info.get('paper_code'),
            'needs_review': True,
            'error': 'exam_id missing in QR',
            'source': 'qr',
        }

    return {
        'exam_id': exam_id,
        'course_code': qr_info.get('course_code'),
        'exam_title': qr_info.get('exam_title'),
        'course_name': qr_info.get('course_name'),
        'omr_count': qr_info.get('omr_count'),
        'classical_count': qr_info.get('classical_count'),
        'paper_code': qr_info.get('paper_code'),
        'needs_review': False,
        'error': None,
        'source': 'qr',
    }

def _decode_with_opencv(image):
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)
    if data:
        return [data]

    try:
        ok, infos, _, _ = detector.detectAndDecodeMulti(image)
        if ok and infos:
            return [info for info in infos if info]
    except Exception:
        pass
    return []

def _decode_with_pyzbar(image):
    results = []
    try:
        from pyzbar.pyzbar import decode
        for item in decode(image):
            if item.data:
                results.append(item.data.decode('utf-8', errors='ignore'))
    except Exception:
        pass
    return results

def _preprocess_variants(gray):
    variants = [gray]
    variants.append(cv2.equalizeHist(gray))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    variants.append(clahe.apply(gray))

    sharp_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    variants.append(cv2.filter2D(gray, -1, sharp_kernel))
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)
    return variants

def _qr_crop_regions(gray):
    h, w = gray.shape[:2]
    return [
        gray,
        gray[0:int(h * 0.4), int(w * 0.45):w],
        gray[0:int(h * 0.35), int(w * 0.55):w],
        gray[0:int(h * 0.45), :],
    ]

def _try_decode_codes(image):
    if image is None or image.size == 0:
        return []

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    results = set()
    for region in _qr_crop_regions(gray):
        for scale in (1, 2, 3, 4, 6, 8):
            scaled = cv2.resize(
                region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC,
            ) if scale > 1 else region

            for variant in _preprocess_variants(scaled):
                for data in _decode_with_opencv(variant):
                    results.add(data)
                for data in _decode_with_pyzbar(variant):
                    results.add(data)
            
            # If we found at least a QR code and a barcode, we can return early
            has_json = any(d.startswith("{") for d in results)
            has_code = any(not d.startswith("{") for d in results)
            if has_json and has_code:
                return list(results)
                
    return list(results)

def _ocr_paper_code(image):
    """Read 'Code: XXXXX' or 'Paper: XXXXX' printed on the answer sheet."""
    if image is None:
        return ''

    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    regions = [
        gray[0:int(h * 0.22), int(w * 0.45):w],
        gray[int(h * 0.10):int(h * 0.24), int(w * 0.60):w],
        gray[int(h * 0.88):h, int(w * 0.05):int(w * 0.95)],
        gray[int(h * 0.92):h, :],
    ]

    try:
        import pytesseract
        from pytesseract import TesseractNotFoundError
        configs = [
            r'--oem 3 --psm 6',
            r'--oem 3 --psm 7',
            r'--oem 3 --psm 11',
        ]
        for region in regions:
            for scale in (4, 6, 8):
                scaled = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                for config in configs:
                    text = pytesseract.image_to_string(scaled, config=config).upper()
                    match = re.search(r'(?:CODE|PAPER|ID)\s*[: ]\s*([A-Z0-9]{6,12})', text)
                    if match:
                        return match.group(1)
                    for code in re.findall(r'\b[A-Z0-9]{8}\b', text):
                        if not code.isdigit():
                            return code
    except TesseractNotFoundError:
        pass
    except Exception:
        pass
    return ''

def _result_from_paper_code(paper_code):
    from evaluation.models import ExamPaper

    exam_paper = ExamPaper.objects.select_related('exam', 'exam__course').filter(
        paper_code=paper_code,
    ).first()
    if not exam_paper:
        return _empty_qr_result(f'Unknown paper code: {paper_code}')

    exam = exam_paper.exam
    layout = exam.get_sheet_layout()
    return {
        'exam_id': exam.id,
        'course_code': exam.course.code,
        'exam_title': exam.title,
        'course_name': exam.course.name,
        'omr_count': layout.get('omr_count') if layout else 0,
        'classical_count': layout.get('classical_count') if layout else 4,
        'paper_code': paper_code,
        'exam_paper_id': exam_paper.id,
        'needs_review': False,
        'error': None,
        'source': 'barcode_or_paper_code',
    }

def read_qr_from_image(image_path):
    """Read exam metadata from QR or Barcode, with paper-code OCR fallback."""
    import os
    if not image_path or not os.path.isfile(image_path):
        return _empty_qr_result(f'Image file not found: {image_path}')

    try:
        image = cv2.imread(image_path)
        if image is None:
            return _empty_qr_result('Cannot read image')
    except Exception as exc:
        return _empty_qr_result(f'Cannot read image: {exc}')

    h, w = image.shape[:2]
    note = ""
    if max(h, w) < 900:
        min_side = min(h, w)
        if min_side < 500:
            note = (
                f'Image is very low resolution ({w}x{h}). '
                'Use a 300 DPI scan or a photo taken closer to the page. '
            )
        else:
            note = f'Low resolution ({w}x{h}) may reduce accuracy. '

    decoded_items = _try_decode_codes(image)
    
    # Try Barcode first (it gives us the specific paper_code)
    for data in decoded_items:
        if not data.startswith("{"):
            # It's likely the barcode (paper_code)
            res = _result_from_paper_code(data)
            if not res['error']:
                if note:
                    res['error'] = note
                    res['needs_review'] = True
                return res

    # Try QR Code second
    for data in decoded_items:
        if data.startswith("{"):
            res = _parse_qr_payload(data)
            if not res['error']:
                if note:
                    res['error'] = note
                    res['needs_review'] = True
                return res

    # Fallback to OCR
    paper_code = _ocr_paper_code(image)
    if paper_code:
        res = _result_from_paper_code(paper_code)
        res['error'] = note + 'QR/Barcode unreadable; matched via text OCR.'
        if note:
            res['needs_review'] = True
        return res

    return _empty_qr_result(
        note + 'QR code/Barcode not found. Print the PDF at 100% scale and scan at 300 DPI, '
        'or photograph the page flat in good light without screenshot compression.'
    )
