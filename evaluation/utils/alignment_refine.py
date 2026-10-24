"""Refine scan alignment after perspective warp using visible form structure."""
import cv2
import numpy as np

from .layout_engine import MCQ_OPTIONS
from .paper_layout import (
    get_classical_score_box_rects,
    get_mcq_bubble_centers,
    get_student_id_box_rects,
)


def _cluster_centers(values, tolerance):
    if not values:
        return []
    values = sorted(values)
    groups = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(sum(group) / len(group))) for group in groups]


def _detect_id_box_rects(warped_gray, layout):
    """Locate student-ID boxes from printed rectangles on the scan."""
    template_rects = get_student_id_box_rects(layout)
    if not template_rects or warped_gray is None:
        return template_rects

    y1 = min(rect[1] for rect in template_rects) - 20
    y2 = max(rect[3] for rect in template_rects) + 20
    x1 = max(0, template_rects[0][0] - 40)
    x2 = min(warped_gray.shape[1], template_rects[-1][2] + 40)

    band = warped_gray[y1:y2, x1:x2]
    if band.size == 0:
        return template_rects

    _, binary = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = bw * bh
        if bw < 20 or bh < 14 or area < 500:
            continue
        aspect = bw / max(bh, 1)
        if not (0.8 < aspect < 1.5):
            continue
        candidates.append((
            x + x1,
            y + y1,
            x + bw + x1,
            y + bh + y1,
        ))

    candidates.sort(key=lambda rect: rect[0])
    if len(candidates) == len(template_rects):
        return candidates

    return template_rects


def refine_student_id_box_rects(warped_gray, layout):
    """Return ID box rects detected from the scan when all boxes are visible."""
    return _detect_id_box_rects(warped_gray, layout)


def _find_bubble_centers_in_row(gray, y_center, x_min, x_max):
    band = gray[
        max(0, int(y_center - 18)):min(gray.shape[0], int(y_center + 18)),
        max(0, int(x_min)):min(gray.shape[1], int(x_max)),
    ]
    if band.size == 0:
        return []

    blur = cv2.GaussianBlur(band, (5, 5), 0)
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=18,
        param1=80,
        param2=14,
        minRadius=4,
        maxRadius=14,
    )
    if circles is None:
        return []

    offset_x = max(0, int(x_min))
    offset_y = max(0, int(y_center - 18))
    found = []
    for cx, cy, _radius in circles[0]:
        found.append((float(cx + offset_x), float(cy + offset_y)))
    found.sort(key=lambda point: point[0])
    return found


def _align_found_circles(template_row, found):
    """Map detected circles to template positions when they are close enough."""
    if len(found) < len(MCQ_OPTIONS):
        return None

    if len(found) > len(MCQ_OPTIONS):
        step = len(found) / len(MCQ_OPTIONS)
        found = [found[int(round(i * step + step / 2 - 1))] for i in range(len(MCQ_OPTIONS))]

    aligned = []
    for (template_cx, template_cy), (found_cx, found_cy) in zip(template_row, found):
        if abs(found_cx - template_cx) > 22 or abs(found_cy - template_cy) > 16:
            return None
        aligned.append((found_cx, found_cy))
    return aligned


def refine_mcq_bubble_centers(warped_gray, layout):
    """Adjust bubble centers row-by-row only when circle detection agrees with template."""
    template_rows = get_mcq_bubble_centers(layout)
    if not template_rows or warped_gray is None:
        return template_rows

    refined_rows = []
    for template_row in template_rows:
        if not template_row:
            refined_rows.append(template_row)
            continue

        y_center = sum(cy for _, cy in template_row) / len(template_row)
        x_min = min(cx for cx, _ in template_row) - 30
        x_max = max(cx for cx, _ in template_row) + 30
        found = _find_bubble_centers_in_row(warped_gray, y_center, x_min, x_max)
        aligned = _align_found_circles(template_row, found)
        refined_rows.append(aligned if aligned is not None else template_row)
    return refined_rows


def refine_classical_score_box_rects(warped_gray, layout):
    """Detect fiducial markers to perfectly align score boxes."""
    template_rects = get_classical_score_box_rects(layout)
    if not template_rects or warped_gray is None:
        return template_rects

    # Find black fiducial squares
    _, binary = cv2.threshold(warped_gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    markers = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        # Expected size ~16x16 pixels. Relaxed bounds to 12-25. Area 120-550.
        if 120 < area < 550 and 10 < w < 25 and 10 < h < 25:
            aspect = w / float(h)
            if 0.7 < aspect < 1.3:
                hull = cv2.convexHull(c)
                hull_area = cv2.contourArea(hull)
                if hull_area > 0 and area / hull_area > 0.8: # Must be a filled square
                    markers.append((x, y, w, h))
    
    if len(markers) >= len(template_rects):
        refined = []
        for i, (tx1, ty1, tx2, ty2) in enumerate(template_rects):
            # Find a marker that is roughly at the same Y level
            expected_y = ty1 + (ty2 - ty1) / 2.0
            best_marker = None
            best_dist = float('inf')
            for (mx, my, mw, mh) in markers:
                my_center = my + mh / 2.0
                dist = abs(my_center - expected_y)
                if dist < 40 and dist < best_dist:
                    best_dist = dist
                    best_marker = (mx, my, mw, mh)
            
            if best_marker:
                mx, my, mw, mh = best_marker
                tw = tx2 - tx1
                th = ty2 - ty1
                
                # The distance from marker edge to box edge is 6 points (~8 pixels)
                # BUT stretching and warping can shift this. To be absolutely safe 
                # and completely avoid the thick black stroke on the left, we skip 14 pixels.
                # We also reduce the width slightly to avoid the right stroke.
                box_x1 = int(mx + mw + 14)
                box_x2 = int(mx + mw + 8) + tw - 6
                box_y1 = int(my + mh / 2.0 - th / 2.0) + 2
                box_y2 = box_y1 + th - 4
                refined.append((box_x1, box_y1, box_x2, box_y2))
            else:
                refined.append((tx1, ty1, tx2, ty2))
        return refined

    # Fallback if markers are not perfectly detected or this is an old scan
    return template_rects
