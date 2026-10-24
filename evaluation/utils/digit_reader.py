"""Digit recognition for classical score boxes (no Tesseract required)."""
import re
import cv2
import numpy as np
import easyocr

_EASYOCR_READER = easyocr.Reader(['en'], gpu=False)

_DIGIT_TEMPLATES = None


def _get_digit_templates(cell_size=64):
    global _DIGIT_TEMPLATES
    if _DIGIT_TEMPLATES is not None:
        return _DIGIT_TEMPLATES

    templates = {}
    for digit in range(21):
        canvas = np.zeros((cell_size, cell_size), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        text = str(digit)
        # Use smaller scale for 2-digit numbers so they fit in the 64x64 cell
        scale = 1.8 if digit < 10 else 1.3
        thickness = 3 if digit < 10 else 2
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        x = max(0, (cell_size - tw) // 2)
        y = (cell_size + th) // 2
        cv2.putText(canvas, text, (x, y), font, scale, 255, thickness)
        templates[digit] = canvas

    _DIGIT_TEMPLATES = templates
    return templates


def _crop_id_box_interior(box_gray):
    """Remove printed box borders before digit extraction."""
    if box_gray.size == 0:
        return box_gray
    h, w = box_gray.shape[:2]
    margin_y = max(2, int(h * 0.12))
    margin_x = max(2, int(w * 0.14))
    crop = box_gray[margin_y:h - margin_y, margin_x:w - margin_x]
    return crop if crop.size else box_gray


def _extract_id_digit_roi(box_gray):
    """Isolate computer font digits cleanly by removing frame lines and noise."""
    if box_gray.size == 0:
        return None
    
    # 1. İçeriği biraz daha agresif kırp (Çerçeve çizgilerinden kurtulmak için)
    h_orig, w_orig = box_gray.shape[:2]
    margin_y = max(3, int(h_orig * 0.14))
    margin_x = max(3, int(w_orig * 0.16))
    interior = box_gray[margin_y:h_orig - margin_y, margin_x:w_orig - margin_x]
    
    if interior.size == 0:
        return None

    # 2. Resmi 4 kat büyüt ki şablon eşleme pikselleri net görsün
    scaled = cv2.resize(interior, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    
    # 3. Sert siyah-beyaz eşiklemesi yap (Arka plan siyah, yazı beyaz olacak)
    _, binary = cv2.threshold(scaled, 120, 255, cv2.THRESH_BINARY_INV)
    
    # 4. 🎯 AKILLI KONTUR FİLTRESİ: Kutuda kalan çizgi pürüzlerini imha et
    # Sadece gerçek rakamın konturunu bulup etrafını temizleyeceğiz
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        # En büyük alana sahip konturu (yani rakamı) bul
        best_cnt = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(best_cnt)
        
        # Eğer çok küçük bir gürültü değilse, sadece o rakamın olduğu bölgeyi kırp al
        if w > 10 and h > 20:
            # Etrafına 4 piksel güvenli beyaz boşluk (pad) bırakarak maskele
            pad = 6
            mask = np.zeros_like(binary)
            cv2.drawContours(mask, [best_cnt], -1, 255, -1)
            # Maske dışındaki her şeyi temizle (tamamen siyah yap, inv olduğu için beyaz alan elensin)
            cleaned = cv2.bitwise_and(binary, mask)
            
            y1 = max(0, y - pad)
            y2 = min(binary.shape[0], y + h + pad)
            x1 = max(0, x - pad)
            x2 = min(binary.shape[1], x + w + pad)
            
            return cleaned[y1:y2, x1:x2]

    return binary


def _score_id_digit(features, digit):
    """Score a digit candidate for student-ID boxes (ignore unreliable hole counts)."""
    holes = features['holes']
    top, mid, bot = features['top'], features['mid'], features['bot']
    left, right, center = features['left'], features['right'], features['center']

    score = 0.0
    if digit == 0:
        if holes == 1 and mid > 0.34 and right > left + 0.1:
            score -= 4.0
        elif mid > 0.28 and abs(mid - bot) < 0.015 and holes == 0:
            score += 6
        elif mid > 0.28 and abs(top - bot) < 0.06 and holes == 0:
            score += 5
        elif mid > 0.285 and holes == 0:
            score += 3
    elif digit == 1:
        if center > 0.62 and features.get('aspect', 1.0) > 1.8:
            score += 9
        elif center > 0.36 and 0.24 < mid < 0.28:
            score += 5
        elif center > 0.33 and mid < 0.26 and abs(top - bot) < 0.012 and top > 0.34:
            score += 7
    elif digit == 2:
        if mid < 0.22 and top > bot + 0.06:
            score += 6
        elif mid < 0.26 and top > 0.33 and bot > 0.28 and abs(top - bot) > 0.03:
            score += 6
        elif mid < 0.24 and top >= bot - 0.02:
            score += 4
        if abs(top - bot) < 0.03 and mid < 0.26:
            score -= 3.0
    elif digit == 4:
        if mid > 0.34 and right > left + 0.12 and top < 0.28:
            score += 8
        elif mid > 0.295 and top > 0.35 and center < 0.40:
            score += 5
        elif center > 0.42 and 0.29 < mid < 0.36 and top > 0.30 and bot > 0.26 and right < 0.32:
            score += 6
        elif mid > 0.30 and right > left:
            score += 3
        if holes == 1 and mid > 0.36 and right > left + 0.1:
            score += 2.0
    elif digit == 3:
        if top > 0.26 and bot > 0.16 and 0.22 < mid < 0.32:
            score += 5
        elif top > bot - 0.04 and mid > 0.24:
            score += 3
    elif digit == 5:
        if top > bot + 0.02 and 0.22 < mid < 0.27:
            score += 4
    elif digit == 6:
        if bot > top - 0.06 and mid > 0.26:
            score += 4
        elif bot > 0.28 and mid > 0.22:
            score += 3
    elif digit == 7:
        if top > bot + 0.05 and mid < 0.24:
            score += 4
    elif digit == 8:
        if 0.22 < mid < 0.38 and abs(top - bot) < 0.12:
            score += 5
        elif mid > 0.26 and top > 0.22:
            score += 3
        if abs(top - bot) < 0.08 and mid < 0.26:
            score -= 2.0
    elif digit == 9:
        if top > 0.24 and bot > 0.16 and mid > 0.20:
            score += 5
        elif top >= bot - 0.10 and mid > 0.22:
            score += 3
        if abs(top - bot) < 0.08 and mid < 0.26:
            score -= 2.0
        if center > 0.40 and mid > 0.30:
            score -= 2.5
    return score


def read_id_box_candidates(box_gray, top_n=4):
    """Return ranked digit candidates for one student-ID box."""
    if box_gray.size == 0:
        return []

    interior = _crop_id_box_interior(box_gray)
    ink_ratio = 1.0 - (float(np.mean(interior)) / 255.0)
    if ink_ratio < 0.015:
        return []

    prepared = _extract_id_digit_roi(box_gray)
    if prepared is None or prepared.size == 0:
        return []

    features = _digit_features(prepared)
    if features is None:
        return []

    scores = {digit: 0.0 for digit in range(21)}
    for digit in range(10):
        scores[digit] = _score_id_digit(features, digit)

    holes = features['holes']
    top, mid, bot = features['top'], features['mid'], features['bot']

    if holes >= 2:
        scores[3] -= 2.0
    if holes == 1 and mid > 0.36 and features['right'] > features['left'] + 0.1:
        scores[0] -= 3.0
        scores[6] -= 1.5
    if abs(top - bot) < 0.08 and mid < 0.26:
        scores[8] -= 2.5
        scores[9] -= 2.5

    norm = cv2.resize(prepared, (64, 64), interpolation=cv2.INTER_AREA)
    template_scores = {}
    for digit, template in _get_digit_templates().items():
        template_score = cv2.matchTemplate(norm, template, cv2.TM_CCOEFF_NORMED).max()
        template_scores[digit] = template_score
        
        if template_score > 0:
            if digit >= 10:
                # Multi-digit numbers have 0 heuristic score. 
                # Give them a massive boost if they match the template well.
                # A good template match for a multi-digit number is very rare by chance.
                boost = 14.0 if template_score > 0.55 else 8.0
                scores[digit] += template_score * boost
            else:
                scores[digit] += template_score * 8.0

    # If the blob is wide, heavily penalize single digits
    if features['aspect'] > 0.8:
        for d in range(10):
            scores[d] -= 4.0
            
    # Also, if a multi-digit template matches exceptionally well (>0.65),
    # suppress single digits because KNN might erroneously give them high heuristic scores
    best_multi_digit = max([digit for digit in range(10, 21)], key=lambda d: template_scores.get(d, 0.0))
    if template_scores.get(best_multi_digit, 0.0) > 0.65:
        for d in range(10):
            scores[d] -= 5.0

    ranked = sorted(
        scores.items(),
        key=lambda item: (item[1], template_scores.get(item[0], 0.0)),
        reverse=True,
    )
    return [(str(digit), score) for digit, score in ranked[:top_n] if score > 0.5]


def _classify_id_digit(roi):
    features = _digit_features(roi)
    if features is None:
        return None, 0.0

    scores = {digit: _score_id_digit(features, digit) for digit in range(10)}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_digit, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score < 2.5:
        return None, 0.0

    confidence = min(0.95, 0.60 + (best_score - second_score) * 0.06 + best_score * 0.03)
    return best_digit, confidence


def _recognize_by_template(prepared):
    if prepared.size == 0:
        return None, 0.0

    norm = cv2.resize(prepared, (64, 64), interpolation=cv2.INTER_AREA)

    best_digit, best_score = None, -1.0
    for digit, template in _get_digit_templates().items():
        score = cv2.matchTemplate(norm, template, cv2.TM_CCOEFF_NORMED).max()
        if score > best_score:
            best_score = score
            best_digit = digit

    if best_score < 0.28:
        return None, best_score
    return best_digit, best_score


def preprocess_digit_image(gray, scale=8):
    if gray.size == 0:
        return gray
    scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(scaled, h=10)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _prepare_score_box(binary):
    """Isolate handwritten digits and remove printed box borders."""
    inv = 255 - binary if np.mean(binary) > 127 else binary.copy()
    h, w = inv.shape[:2]
    margin_y = max(4, int(h * 0.12))
    margin_x = max(4, int(w * 0.10))
    crop = inv[margin_y:h - margin_y, margin_x:w - margin_x]
    if crop.size == 0:
        return inv

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(crop, cv2.MORPH_CLOSE, kernel, iterations=1)


def _count_holes(roi):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    merged = cv2.dilate(roi, kernel, iterations=1)
    contours, hierarchy = cv2.findContours(merged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    holes = 0
    for idx, item in enumerate(hierarchy[0]):
        if item[3] != -1 and cv2.contourArea(contours[idx]) > 20:
            holes += 1
    return holes


def _digit_features(roi):
    h, w = roi.shape[:2]
    if h == 0 or w == 0:
        return None

    norm = cv2.resize(roi, (32, 32), interpolation=cv2.INTER_AREA)
    ink = (norm > 0).astype(np.uint8)
    rows = ink.sum(axis=1).astype(np.float32)
    cols = ink.sum(axis=0).astype(np.float32)
    total = max(float(rows.sum()), 1.0)

    return {
        'holes': _count_holes(roi),
        'aspect': h / max(w, 1),
        'width_ratio': w / max(h, 1),
        'top': float(rows[:10].sum()) / total,
        'mid': float(rows[11:21].sum()) / total,
        'bot': float(rows[22:].sum()) / total,
        'left': float(cols[:11].sum()) / total,
        'right': float(cols[21:].sum()) / total,
        'center': float(cols[10:22].sum()) / total,
    }


def _score_digit_candidate(features, digit):
    holes = features['holes']
    aspect = features['aspect']
    width_ratio = features['width_ratio']
    top, mid, bot = features['top'], features['mid'], features['bot']
    center = features['center']
    left, right = features['left'], features['right']

    score = 0.0
    if digit == 0:
        if holes == 1 and center > 0.60:
            score -= 5.0
        elif holes == 1 and mid > 0.34 and right > left + 0.1:
            score -= 4.0
        score += 3.0 if holes >= 1 else 0.0
        score += 1.0 if 0.6 < aspect < 1.5 else 0.0
        score += 2.5 if holes == 0 and center < 0.35 and (left + right) > 0.4 else 0.0
        score -= 2.0 if center > 0.45 else 0.0
        score -= 2.0 if top < 0.2 or bot < 0.2 else 0.0
    elif digit == 1:
        score += 2.0 if aspect > 1.45 and center > 0.35 else 0.0
        score += 2.0 if aspect > 1.3 and holes == 0 and left < 0.35 and right < 0.35 else 0.0
        score += 1.5 if holes == 0 and top < 0.45 else 0.0
        score -= 2.0 if top > 0.34 and mid > 0.28 else 0.0
    elif digit == 2:
        score += 2.0 if top > 0.3 and bot > 0.3 and right > 0.2 and left > 0.2 else 0.0
        score -= 2.0 if holes > 0 else 0.0
    elif digit == 3:
        score += 2.0 if right > 0.35 and left < 0.25 else 0.0
        score -= 2.0 if holes > 0 else 0.0
    elif digit == 4:
        score += 2.0 if top > 0.25 and right > 0.25 and bot > 0.25 else 0.0
        score += 1.0 if holes == 1 else 0.0
    elif digit == 5:
        score += 2.0 if top > 0.25 and left > 0.2 and bot > 0.25 else 0.0
        score -= 2.0 if holes > 0 else 0.0
    elif digit == 6:
        score += 3.0 if holes == 1 and bot > 0.3 else 0.0
        score += 2.0 if holes == 0 and left > 0.3 and bot > 0.3 and center < 0.4 else 0.0
        score += 1.0 if left > 0.35 else 0.0
    elif digit == 7:
        score += 2.0 if aspect > 0.8 and top > 0.35 and left > 0.15 else 0.0
        score -= 2.0 if bot > 0.5 or center > 0.6 else 0.0
    elif digit == 8:
        score += 3.0 if holes >= 2 else 0.0
        score += 1.5 if holes == 1 and center > 0.35 else 0.0
        score += 1.5 if holes == 0 and center > 0.35 and top > 0.3 and bot > 0.3 else 0.0
    elif digit == 9:
        score += 3.0 if holes == 1 and top > 0.3 else 0.0
        score += 2.0 if holes == 0 and right > 0.3 and top > 0.3 and center < 0.4 else 0.0
        score += 1.0 if right > 0.35 else 0.0

    if width_ratio > 1.2 and digit in (0, 1):
        score -= 1.0
    return score


def _classify_digit_roi(roi):
    features = _digit_features(roi)
    if features is None:
        return None, 0.0

    scores = {digit: _score_digit_candidate(features, digit) for digit in range(10)}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_digit, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    if margin < 0.35 and best_score == second_score:
        if features['holes'] >= 1 and scores.get(0, 0) == best_score:
            best_digit = 0
        elif features['mid'] > 0.30 and scores.get(0, 0) >= second_score - 0.1:
            best_digit = 0

    if best_score < 1.5 or (margin < 0.25 and best_score < 2.5):
        return None, max(0.0, best_score / 5.0)

    confidence = min(0.95, 0.58 + margin * 0.1 + best_score * 0.03)
    return best_digit, confidence


def _split_by_column_gap(roi):
    h, w = roi.shape[:2]
    if w < h * 1.1:
        return [roi]

    col_ink = roi.sum(axis=0).astype(np.float32)
    if col_ink.max() == 0:
        return [roi]

    start = w // 5
    end = 4 * w // 5
    window = col_ink[start:end]
    if window.size == 0:
        return [roi]

    split_at = start + int(np.argmin(window))
    if col_ink[split_at] > col_ink.max() * 0.2:
        return [roi]

    left = roi[:, :split_at]
    right = roi[:, split_at:]
    parts = []
    for part in (left, right):
        if part.size and np.sum(part > 0) > 30:
            parts.append(part)
    return parts if len(parts) > 1 else [roi]


def _split_digit_rois(prepared):
    h, w = prepared.shape[:2]
    min_area = max(50, (h * w) * 0.05)
    contours, _ = cv2.findContours(prepared, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bh < h * 0.25 or bw < w * 0.12:
            continue
        roi = prepared[y:y + bh, x:x + bw]
        for part in _split_by_column_gap(roi):
            candidates.append((x, part, cv2.countNonZero(part)))

    if not candidates and np.sum(prepared > 0) > min_area:
        for part in _split_by_column_gap(prepared):
            candidates.append((0, part, cv2.countNonZero(part)))

    if not candidates:
        return []

    candidates.sort(key=lambda item: item[2], reverse=True)
    max_digits = 2 if w > h * 1.05 else 1
    selected = sorted(candidates[:max_digits], key=lambda item: item[0])
    return [roi for _, roi, _ in selected]


def _crop_score_box_interior(box_gray):
    """Interior crop for classical score boxes (keep more ink than ID boxes)."""
    if box_gray.size == 0:
        return box_gray
    h, w = box_gray.shape[:2]
    margin_y = max(2, int(h * 0.08))
    margin_x = max(4, int(w * 0.1))
    crop = box_gray[margin_y:h-margin_y, margin_x:w-margin_x]
    return crop if crop.size else box_gray


def _split_gray_score_digits(box_gray):
    """Extract individual digits using contours, splitting wide connected digits."""
    interior = _crop_score_box_interior(box_gray)
    h, w = interior.shape[:2]
    if h == 0 or w == 0:
        return [interior]
        
    _, binary = cv2.threshold(interior, 190, 255, cv2.THRESH_BINARY_INV)
    
    # ERASE BORDERS explicitly to disconnect digits from the stroke
    for col in range(w):
        if np.count_nonzero(binary[:, col]) > h * 0.4:
            binary[:, col] = 0
        elif np.count_nonzero(binary[:, col]) == 0:
            pass
        else:
            break
            
    for col in range(w - 1, -1, -1):
        if np.count_nonzero(binary[:, col]) > h * 0.4:
            binary[:, col] = 0
        elif np.count_nonzero(binary[:, col]) == 0:
            pass
        else:
            break

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    if hierarchy is not None:
        for i, cnt in enumerate(contours):
            # Only process top-level contours
            if hierarchy[0][i][3] != -1:
                continue
            
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            if cw * ch < 20 or ch < 6:
                continue

            # VERY ROBUST BORDER FILTER:
            # A border is extremely tall (ch > h * 0.85), thin (cw < w * 0.2), 
            # and touching the far left or far right edges (cx < w*0.1 or cx+cw > w*0.9)
            if ch > h * 0.85 and cw < w * 0.2 and (cx < w * 0.1 or cx + cw > w * 0.9):
                print(f"DEBUG: ROBUST BORDER FILTER at cx={cx}, cw={cw}, ch={ch}")
                continue
                
            has_hole = (hierarchy[0][i][2] != -1)
            candidates.append((cx, cy, cw, ch, has_hole))

    candidates.sort(key=lambda c: c[0])
    parts = []

    for cx, cy, cw, ch, has_hole in candidates:
        roi = binary[:, cx:cx+cw]
        
        # Split wide contours
        if cw > w * 0.45 and cw > 12:
            col_ink = np.sum(roi, axis=0) / 255.0
            mid_start = int(cw * 0.3)
            mid_end = int(cw * 0.7)
            if mid_end > mid_start:
                valley_idx = mid_start + int(np.argmin(col_ink[mid_start:mid_end]))
                if col_ink[valley_idx] <= 2:
                    crop1 = roi[:, :valley_idx]
                    crop2 = roi[:, valley_idx:]
                    if np.count_nonzero(crop1) > 10:
                        parts.append(crop1)
                    if np.count_nonzero(crop2) > 10:
                        parts.append(crop2)
                    continue
    
    if not parts:
        return [binary]
    return parts


def _pad_to_square(img):
    h, w = img.shape[:2]
    if h == w:
        return img
    size = max(h, w)
    pad_h = (size - h) // 2
    pad_w = (size - w) // 2
    padded = cv2.copyMakeBorder(img, pad_h, size - h - pad_h, pad_w, size - w - pad_w, cv2.BORDER_CONSTANT, value=0)
    return padded

def _read_score_part(part_binary):
    """Read one digit from a split classical score region."""
    h, w = part_binary.shape[:2]
    if w == 0 or h == 0:
        return "", 35.0, True

    if w <= 8 and h / w > 1.5:
        print(f"DEBUG PART: Very thin part, assuming 1")
        return "1", 85.0, False

    # Template matching on already-inverted binary image
    norm = cv2.resize(part_binary, (64, 64), interpolation=cv2.INTER_AREA)
    best_digit = None
    best_score = -1.0
    for digit, template in _get_digit_templates().items():
        if digit >= 10: continue # Single parts are only 0-9
        score = cv2.matchTemplate(norm, template, cv2.TM_CCOEFF_NORMED).max()
        if score > best_score:
            best_score = score
            best_digit = str(digit)
            
    if best_digit and best_score >= 0.45:
        conf = min(95.0, 55 + best_score * 40)
        print(f"DEBUG PART: Template matched digit='{best_digit}' with score={best_score:.3f}")
        return best_digit, conf, False

    feat_digit, feat_score = _classify_digit_roi(part_binary)
    print(f"DEBUG PART: KNN matched digit='{feat_digit}' with conf={feat_score:.3f}")
    if feat_digit is not None:
        return str(feat_digit), round(feat_score * 100, 1), False

    return "", 35.0, True


def _pick_score_digit_from_candidates(candidates, interior=None):
    if not candidates:
        return None, 0.0
    best_digit, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0

    if interior is not None:
        prepared = _extract_id_digit_roi(interior)
        feats = _digit_features(prepared) if prepared is not None else None
        if feats:
            top, mid, bot = feats['top'], feats['mid'], feats['bot']
            seven_score = next((c[1] for c in candidates if c[0] == '7'), None)
            if (
                best_digit == '2'
                and seven_score is not None
                and float(best_score) - float(seven_score) <= 3.0
                and top > 0.45
                and mid < 0.25
            ):
                return '7', float(seven_score)
            if best_digit in ('8', '4', '3') and 0.27 < mid < 0.42 and top > bot + 0.12:
                return '5', max(float(second_score), 4.0)

    if best_score - second_score < 0.35 and len(candidates) > 1:
        second_digit = candidates[1][0]
        if best_digit == '8' and second_digit == '3':
            return '3', float(second_score)
    return best_digit, float(best_score)


def _classify_score_digit(roi):
    """Classify one typed/handwritten digit in a classical score box."""
    tmpl_digit, tmpl_score = _recognize_by_template(roi)
    if tmpl_digit is not None and tmpl_score >= 0.32:
        return tmpl_digit, min(0.95, 0.55 + tmpl_score * 0.55)

    digit, conf = _classify_digit_roi(roi)
    if digit is None:
        return None, 0.0

    features = _digit_features(roi)
    if features and digit == 6 and features['holes'] == 1:
        if abs(features['top'] - features['bot']) < 0.14 and features['mid'] > 0.34:
            return 0, max(conf, 0.72)

    if features and digit == 5 and features['holes'] == 0:
        tmpl_three, three_score = None, -1.0
        norm = cv2.resize(roi, (64, 64), interpolation=cv2.INTER_AREA)
        three_canvas = _get_digit_templates()[3]
        three_score = cv2.matchTemplate(norm, three_canvas, cv2.TM_CCOEFF_NORMED).max()
        five_score = cv2.matchTemplate(norm, _get_digit_templates()[5], cv2.TM_CCOEFF_NORMED).max()
        if three_score >= 0.30 and three_score + 0.05 >= five_score:
            return 3, max(conf, min(0.95, 0.5 + three_score * 0.5))

    return digit, conf


def _read_score_digit_from_features(part):
    prepared = _extract_id_digit_roi(part)
    if prepared is None or prepared.size == 0:
        return '', 35.0, True
    feats = _digit_features(prepared)
    if not feats:
        return '', 35.0, True

    top, mid, bot = feats['top'], feats['mid'], feats['bot']
    if abs(top - bot) < 0.12 and mid < 0.28:
        return '0', 75.0, False
    if 0.27 < mid < 0.38 and top > bot + 0.05:
        return '5', 75.0, False
    return '', 35.0, True


def _read_single_score_interior(interior):
    norm = cv2.resize(interior, (64, 64), interpolation=cv2.INTER_AREA)
    best_digit = None
    best_score = -1.0
    for digit, template in _get_digit_templates().items():
        score = cv2.matchTemplate(norm, template, cv2.TM_CCOEFF_NORMED).max()
        if score > best_score:
            best_score = score
            best_digit = str(digit)
            
    if best_digit and best_score >= 0.45:
        conf = min(95.0, 55 + best_score * 40)
        print(f"DEBUG SINGLE INTERIOR: Template matched digit='{best_digit}' with score={best_score:.3f}")
        return best_digit, conf, False

    feat_digit, feat_conf, feat_blank = _read_score_digit_from_features(interior)
    if not feat_blank and feat_digit:
        return feat_digit, feat_conf, False

    digit, conf, blank = read_single_digit_from_box(interior)
    if not blank and digit:
        return digit, conf, False

    return "", 35.0, True


def read_number_from_box(box_gray, max_value=100):
    """
    Read handwritten score from a box.
    """
    interior = _crop_score_box_interior(box_gray)
    if interior is None:
        return 0, 0.0, True

    _, binary_mask = cv2.threshold(interior, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_ratio = np.count_nonzero(binary_mask) / float(binary_mask.size)
    print(f"DEBUG SCORE BOX: ink_ratio={ink_ratio:.4f}")

    if ink_ratio < 0.015:
        print(f"DEBUG SCORE BOX: BLANK detected")
        return 0, 85.0, True

    # 1. Primary method: EasyOCR on the entire cropped region
    text, conf = read_number_with_easyocr(box_gray)
    if text:
        try:
            val = int(text)
            if val <= max_value:
                return val, min(95.0, conf), False
            else:
                print(f"DEBUG SCORE BOX: OCR read {val} > {max_value}, falling back")
        except ValueError:
            pass

    # 2. Fallback: Digit splitting + KNN/Template
    parts_binary = _split_gray_score_digits(box_gray)
    digits = []
    total_conf = 0.0

    for p in parts_binary:
        d, c, b = _read_score_part(p)
        if not b and d:
            if str(d) != 'None':
                digits.append(str(d))
                total_conf += c

    if len(digits) == 0:
        _, inv_binary = cv2.threshold(interior, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        d2, c2, b2 = _read_single_score_interior(interior)
        if not b2 and d2:
            val = int(d2)
            return (val if val <= max_value else 0), c2, False
        return 0, 0.0, True

    val_str = "".join(digits)
    avg_conf = total_conf / len(digits)

    try:
        val = int(val_str)
        if val > max_value:
            return val, min(avg_conf, 40.0), False
        return val, avg_conf, False
    except ValueError:
        return 0, 0.0, True


def _pick_id_digit_from_candidates(candidates):
    """Pick the best digit from ranked ID-box candidates."""
    if not candidates:
        return '', 0.0, True

    best_digit, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0
    margin = best_score - second_score

    if best_score < 2.5:
        return '', 35.0, True
    if margin < 0.6 and best_score < 4.5:
        return best_digit, round(min(70.0, 40 + best_score * 5), 1), False

    confidence = min(95.0, 55 + best_score * 4 + margin * 3)
    return best_digit, round(confidence, 1), False


def read_number_with_easyocr(box_gray):
    """
    Safely reads a potentially multi-digit number using EasyOCR.
    Expects standard grayscale image (ink is dark).
    """
    h_o, w_o = box_gray.shape[:2]
    if h_o == 0 or w_o == 0:
        return "", 0.0

    # Mask borders gently
    cleaned = box_gray.copy()
    pad_y = max(1, int(h_o * 0.06))
    pad_x = max(1, int(w_o * 0.06))
    cleaned[:pad_y, :] = 255
    cleaned[-pad_y:, :] = 255
    cleaned[:, :pad_x] = 255
    cleaned[:, -pad_x:] = 255

    # Use Otsu's thresholding for robust binarization
    _, binary = cv2.threshold(cleaned, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Scale up massively. EasyOCR likes text to be 30-50px tall. 
    # Our box is ~37px tall, digits are ~20px tall. 3x scaling is good.
    prepared = cv2.resize(binary, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    h_p, w_p = prepared.shape
    results = _EASYOCR_READER.readtext(prepared, allowlist='0123456789')
    if not results:
        # Fallback: bypass CRAFT text detector and force recognize on the whole image
        results = _EASYOCR_READER.recognize(prepared, horizontal_list=[[0, w_p, 0, h_p]], free_list=[], allowlist='0123456789')
        
    if results:
        # Sort by x coordinate to read left-to-right
        results.sort(key=lambda x: x[0][0][0])
        full_text = ""
        total_conf = 0.0
        
        for bbox, text, conf in results:
            found = re.sub(r'[^0-9]', '', text)
            if found:
                full_text += found
                total_conf += conf
                
        if full_text:
            return full_text, (total_conf / len(results)) * 100.0
            
    return "", 0.0

def read_single_digit_from_box(box_gray):
    """
    Student-ID kutusundaki rakamı EasyOCR ile okur.
    Sıfırların (0) halka yapısını kaçırmamak için orijinal renk dengesi korunmuştur.
    """
    if box_gray.size == 0:
        return '', 0.0, True

    # 1. Boş kutu kontrolü (İnanılmaz hassas - Sıfırları kaçırmamak için)
    h_o, w_o = box_gray.shape[:2]
    check_area = box_gray[int(h_o*0.15):int(h_o*0.85), int(w_o*0.15):int(w_o*0.85)]
    ink_ratio = 1.0 - (float(np.mean(check_area)) / 255.0) if check_area.size else 0.0
    if ink_ratio < 0.0005:  
        return '', 85.0, True

    try:
        # 2. Çerçeve çizgilerini BEYAZA boyayarak imha etme (Arka plan beyaz kalacak)
        cleaned = box_gray.copy()
        pad_y = max(1, int(h_o * 0.08))
        pad_x = max(1, int(w_o * 0.08))
        cleaned[:pad_y, :] = 255
        cleaned[-pad_y:, :] = 255
        cleaned[:, :pad_x] = 255
        cleaned[:, -pad_x:] = 255

        # 3. 🎯 SIFIRLARI OKUTMA KONTRASTI:
        # Resmi ters çevirmiyoruz! Yazı SİYAH, arka plan BEYAZ kalıyor.
        # Sadece kontrastı arttırmak için 140'ın altındaki gri pikselleri tam siyah (0) yapıyoruz.
        contrast_boost = np.where(cleaned < 140, 0, 255).astype(np.uint8)
        
        # EasyOCR'ın halkanın içini net görmesi için resmi 3 kat büyütüyoruz
        prepared = cv2.resize(contrast_boost, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        # Hafif pürüzleri temizlemek için çok hafif blur
        prepared = cv2.medianBlur(prepared, 3)

        # 4. EasyOCR ile Okuma
        results = _EASYOCR_READER.readtext(prepared, allowlist='0123456789')
        print("OCR RAW:", results)
        
        if results:
            text = results[0][1]
            conf = float(results[0][2] * 100)
            found = re.sub(r'[^0-9]', '', text)
            if found:
                return found[0], round(conf, 1), False
    except Exception as e:
        print(f"EasyOCR Hatası: {e}")
        pass

    # 5. Fallback: Eski şablon motoru
    prepared_roi = _extract_id_digit_roi(box_gray)
    if prepared_roi is not None and prepared_roi.size:
        digit, score = _recognize_by_template(prepared_roi)
        if digit is not None:
            return str(digit), 70.0, False

    return '', 35.0, True

def _extract_clean_ocr_roi(box_gray):
    """Kutunun içini akıllıca kırpar, büyütür ve Tesseract için hazırlar."""
    if box_gray.size == 0:
        return None
    
    # Çerçeve çizgilerinden kurtulmak için kenarlardan %12 kırpıyoruz
    h, w = box_gray.shape[:2]
    margin_y = max(2, int(h * 0.12))
    margin_x = max(2, int(w * 0.12))
    interior = box_gray[margin_y:h - margin_y, margin_x:w - margin_x]
    
    if interior.size == 0:
        return None
        
    # Tesseract'ın küçük fontları rahat okuması için resmi 3 kat büyütüyoruz
    scaled = cv2.resize(interior, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Yumuşatma uygulayıp net bir siyah-beyaz çıktı alıyoruz
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return binary