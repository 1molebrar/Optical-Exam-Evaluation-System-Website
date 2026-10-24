"""Map answer-sheet layout coordinates to warped scan pixels."""
from .layout_engine import (
    compute_sheet_layout,
    get_student_id_bubble_positions_pdf,
)

DEFAULT_LAYOUT = compute_sheet_layout(0, 4)

def _layout(layout=None):
    return layout or DEFAULT_LAYOUT

def pdf_point_to_pixel(x, y_bottom, layout):
    page_w = layout['page_width']
    page_h = layout['page_height']
    out_w = layout['warp_width']
    out_h = layout['warp_height']
    px = x / page_w * out_w
    py = (1.0 - y_bottom / page_h) * out_h
    return px, py

def pdf_rect_to_pixels(x, y_bottom, width, height, layout):
    x1, y_top = pdf_point_to_pixel(x, y_bottom + height, layout)
    x2, y_bottom_px = pdf_point_to_pixel(x + width, y_bottom, layout)
    return int(x1), int(y_top), int(x2), int(y_bottom_px)

def get_student_id_bubble_centers(layout=None):
    layout = _layout(layout)
    centers = []
    # positions_pdf returns a list of columns. Each column has 10 (0-9) positions.
    for col in get_student_id_bubble_positions_pdf(layout):
        pixel_col = []
        for cx, cy, _radius in col:
            px, py = pdf_point_to_pixel(cx, cy, layout)
            pixel_col.append((int(px), int(py)))
        centers.append(pixel_col)
    return centers

def get_ocr_student_id_rect(layout=None):
    # Returns the rectangle for the "Öğrenci No" info table cell
    layout = _layout(layout)
    from .layout_engine import CONTENT_LEFT, INFO_COL_WIDTHS, INFO_TABLE_BOTTOM, INFO_ROW_HEIGHT
    x = CONTENT_LEFT + INFO_COL_WIDTHS[0]
    y = INFO_TABLE_BOTTOM
    w = INFO_COL_WIDTHS[1]
    h = INFO_ROW_HEIGHT
    return pdf_rect_to_pixels(x, y, w, h, layout)

def get_classical_score_box_rects(layout=None):
    layout = _layout(layout)
    rects = []
    for rect in layout.get('classical_score_rects', []):
        x, y_bottom, width, height = rect
        rects.append(pdf_rect_to_pixels(x, y_bottom, width, height, layout))
    return rects

def get_mcq_bubble_centers(layout=None):
    layout = _layout(layout)
    centers = []
    for row in layout.get('mcq_bubble_centers', []):
        pixel_row = []
        for cx, cy in row:
            px, py = pdf_point_to_pixel(cx, cy, layout)
            pixel_row.append((int(px), int(py)))
        centers.append(pixel_row)
    return centers

def get_student_id_box_rects(layout=None):
    layout = _layout(layout)
    from .layout_engine import get_student_id_bubble_positions_pdf
    positions = get_student_id_bubble_positions_pdf(layout)
    box_width = layout.get('bubble_spacing_x', 11.5)
    box_height = 16
    
    rects = []
    for col_positions in positions:
        bx, by, br = col_positions[0]
        box_y = by + br + 4
        box_x = bx - box_width / 2
        
        x1, y1, x2, y2 = pdf_rect_to_pixels(box_x, box_y, box_width, box_height, layout)
        rects.append((x1, y1, x2, y2))
    return rects
