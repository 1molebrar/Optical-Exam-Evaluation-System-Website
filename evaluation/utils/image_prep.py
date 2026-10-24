"""Shared image loading and perspective correction for scan processing."""
import os
import cv2
import numpy as np

from .layout_engine import WARP_WIDTH, WARP_HEIGHT

MARKER_MIN_AREA = 400
MARKER_MAX_AREA = 12000
MARKER_MAX_SIDE = 90


def _square_candidates(gray):
    """Return square marker candidates as (cx, cy, area)."""
    h, w = gray.shape[:2]
    work = gray
    scale = 1.0
    max_dim = 1800
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        work = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    wh, ww = work.shape[:2]
    blurred = cv2.GaussianBlur(work, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    squares = []
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < MARKER_MIN_AREA or area > MARKER_MAX_AREA:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw > MARKER_MAX_SIDE or bh > MARKER_MAX_SIDE:
            continue
        aspect = bw / max(bh, 1)
        if not (0.75 < aspect < 1.33):
            continue
        cx = (x + bw / 2.0) / scale
        cy = (y + bh / 2.0) / scale
        squares.append((cx, cy, area))

    return squares, w, h


def _corner_band(cx, cy, ww, wh, corner):
    if corner == 'tl':
        return cx < ww * 0.18 and cy < wh * 0.14
    if corner == 'tr':
        return cx > ww * 0.82 and cy < wh * 0.14
    if corner == 'bl':
        return cx < ww * 0.18 and cy > wh * 0.86
    if corner == 'br':
        return cx > ww * 0.82 and cy > wh * 0.86
    return False


def _pick_corner_marker(squares, ww, wh, corner, used):
    """Pick the darkest square marker closest to a page corner."""
    candidates = []
    for idx, (cx, cy, area) in enumerate(squares):
        if idx in used:
            continue
        if not _corner_band(cx, cy, ww, wh, corner):
            continue
        if corner == 'tl':
            dist = (cx - 0) ** 2 + (cy - 0) ** 2
        elif corner == 'tr':
            dist = (cx - ww) ** 2 + (cy - 0) ** 2
        elif corner == 'br':
            dist = (cx - ww) ** 2 + (cy - wh) ** 2
        else:
            dist = (cx - 0) ** 2 + (cy - wh) ** 2
        candidates.append((dist, idx, cx, cy))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    _, idx, cx, cy = candidates[0]
    used.add(idx)
    return np.array([cx, cy], dtype=np.float32)


def _infer_missing_corner(corners):
    """Infer a missing corner from the other three page markers."""
    tl, tr, br, bl = corners
    if tl is None and tr is not None and br is not None and bl is not None:
        return np.array([bl[0] - br[0] + tr[0], tr[1]], dtype=np.float32)
    if tr is None and tl is not None and br is not None and bl is not None:
        return np.array([br[0] - bl[0] + tl[0], tl[1]], dtype=np.float32)
    if bl is None and tl is not None and tr is not None and br is not None:
        return np.array([tl[0] - tr[0] + br[0], br[1]], dtype=np.float32)
    if br is None and tl is not None and tr is not None and bl is not None:
        return np.array([tr[0] - tl[0] + bl[0], bl[1]], dtype=np.float32)
    return None


def _find_dark_square_markers(gray):
    """Find four corner alignment markers (filled black squares)."""
    squares, w, h = _square_candidates(gray)
    if len(squares) < 3:
        return None

    used = set()
    tl = _pick_corner_marker(squares, w, h, 'tl', used)
    tr = _pick_corner_marker(squares, w, h, 'tr', used)
    br = _pick_corner_marker(squares, w, h, 'br', used)
    bl = _pick_corner_marker(squares, w, h, 'bl', used)

    corners = [tl, tr, br, bl]
    missing = sum(point is None for point in corners)
    if missing == 1:
        inferred = _infer_missing_corner(corners)
        for idx, point in enumerate(corners):
            if point is None:
                corners[idx] = inferred
    elif missing > 1:
        return None

    return np.array(corners, dtype=np.float32)


def detect_alignment_markers(gray):
    """Detect four corner alignment markers for perspective correction."""
    markers = _find_dark_square_markers(gray)
    if markers is not None:
        return markers

    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    min_area = max(80, (min(w, h) * 0.01) ** 2)
    max_area = max(2500, (min(w, h) * 0.12) ** 2)
    markers = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if min_area < area < max_area and 0.8 < bw / max(bh, 1) < 1.2:
            markers.append((x + bw // 2, y + bh // 2))
    if len(markers) >= 4:
        markers = sorted(markers, key=lambda point: (point[1], point[0]))
        top = sorted(markers[:2], key=lambda point: point[0])
        bottom = sorted(markers[2:4], key=lambda point: point[0])
        return np.array([top[0], top[1], bottom[1], bottom[0]], dtype=np.float32)
    return None


def correct_perspective(img, corners, output_size=(WARP_WIDTH, WARP_HEIGHT), dst_corners=None):
    if corners is None:
        return img
    if dst_corners is None:
        from .layout_engine import PAGE_WIDTH, PAGE_HEIGHT, get_alignment_marker_centers_warp
        dst_corners = get_alignment_marker_centers_warp({
            'page_width': PAGE_WIDTH,
            'page_height': PAGE_HEIGHT,
            'warp_width': output_size[0],
            'warp_height': output_size[1],
        })
    dst = np.array(dst_corners, dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(img, matrix, output_size)


def load_and_warp(image_path, output_size=(WARP_WIDTH, WARP_HEIGHT)):
    """Load a scan and warp it to the canonical answer-sheet layout."""
    if not image_path or not os.path.isfile(image_path):
        return {
            'gray': None,
            'warped': None,
            'markers_found': False,
            'error': f'Image file not found: {image_path}',
        }

    try:
        img = cv2.imread(image_path)
        if img is None:
            return {
                'gray': None,
                'warped': None,
                'markers_found': False,
                'error': 'Could not read image',
            }
    except Exception as exc:
        return {
            'gray': None,
            'warped': None,
            'markers_found': False,
            'error': f'Could not read image: {exc}',
        }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    markers = detect_alignment_markers(gray)
    if markers is not None:
        warped = correct_perspective(gray, markers, output_size=output_size)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        warped = clahe.apply(warped)
        return {
            'gray': gray,
            'warped': warped,
            'markers_found': True,
            'error': None,
        }

    resized = cv2.resize(gray, output_size)
    return {
        'gray': gray,
        'warped': resized,
        'markers_found': False,
        'error': None,
    }
