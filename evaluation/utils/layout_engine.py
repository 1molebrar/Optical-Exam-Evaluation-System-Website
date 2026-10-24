"""Compute answer-sheet layout from OMR/classical question counts for Topkapi Template."""
from reportlab.lib.pagesizes import A4

PAGE_WIDTH, PAGE_HEIGHT = A4
WARP_WIDTH = 800
WARP_HEIGHT = 1000
MARKER_SIZE = 15
MARKER_INSET = 30

CONTENT_LEFT = 42
CONTENT_RIGHT = PAGE_WIDTH - 42
CONTENT_WIDTH = CONTENT_RIGHT - CONTENT_LEFT

# Legacy options
MCQ_OPTIONS = ['A', 'B', 'C', 'D', 'E']

# We need 11 columns for the student ID.
STUDENT_ID_LENGTH = 11

# Top header geometry
TOP_BOX_TOP = PAGE_HEIGHT - 45
BARCODE_BOX_WIDTH = 180
BARCODE_BOX_HEIGHT = 45
BARCODE_BOX_X = CONTENT_RIGHT - BARCODE_BOX_WIDTH

SUBHEADER_TOP = TOP_BOX_TOP - 90

# Student Info Table
INFO_TABLE_TOP = SUBHEADER_TOP - 20
INFO_COL_WIDTHS = [204, 130, 110, CONTENT_WIDTH - 204 - 130 - 110]
INFO_HEADER_HEIGHT = 20
INFO_ROW_HEIGHT = 30
INFO_TABLE_BOTTOM = INFO_TABLE_TOP - INFO_HEADER_HEIGHT - INFO_ROW_HEIGHT

# Bubble sheet
BUBBLE_SHEET_TOP = INFO_TABLE_BOTTOM - 20
BUBBLE_RADIUS = 5.5
BUBBLE_SPACING_X = 11.5
BUBBLE_SPACING_Y = 12
BUBBLE_SHEET_BOTTOM = BUBBLE_SHEET_TOP - 20 - 10 * BUBBLE_SPACING_Y

# Score Sheet
SCORE_SHEET_TOP = BUBBLE_SHEET_BOTTOM - 20
SCORE_HEADER_HEIGHT_1 = 15
SCORE_HEADER_HEIGHT_2 = 18
SCORE_ROW_HEIGHT = 20
SCORE_TABLE_BOTTOM = SCORE_SHEET_TOP - SCORE_HEADER_HEIGHT_1 - SCORE_HEADER_HEIGHT_2 - SCORE_ROW_HEIGHT

# Define how classical scores are laid out dynamically if needed, 
# but we will try to make it look exactly like the template for up to 4 questions.

def compute_sheet_layout(omr_count=0, classical_count=4, questions=None):
    """Return layout dict used for PDF generation and scan detection."""
    
    # We will use this layout dict for the pipeline to know where bubbles are.
    layout = {
        'page_width': PAGE_WIDTH,
        'page_height': PAGE_HEIGHT,
        'warp_width': WARP_WIDTH,
        'warp_height': WARP_HEIGHT,
        'content_left': CONTENT_LEFT,
        'content_right': CONTENT_RIGHT,
        'content_width': CONTENT_WIDTH,
        'omr_count': omr_count,
        'classical_count': classical_count,
        
        # Student ID grid info
        'student_id_length': STUDENT_ID_LENGTH,
        'student_id_grid_x': CONTENT_LEFT + 20,
        'student_id_grid_top': BUBBLE_SHEET_TOP - 20,
        'bubble_radius': BUBBLE_RADIUS,
        'bubble_spacing_x': BUBBLE_SPACING_X,
        'bubble_spacing_y': BUBBLE_SPACING_Y,
        
        # Legacy mappings for scan helpers if needed
        'qr_x': BARCODE_BOX_X,
        'qr_top': TOP_BOX_TOP,
        'qr_size': 45,
    }

    mcq_bubble_centers = []
    classical_score_rects = []
    
    # Calculate dynamic question layout
    if questions is None:
        questions = []
        for i in range(1, omr_count + 1):
            questions.append({'question_number': i, 'question_type': 'omr', 'points': 1})
        for i in range(1, classical_count + 1):
            questions.append({'question_number': omr_count + i, 'question_type': 'classical', 'points': 1})

    y_cursor = BUBBLE_SHEET_BOTTOM - 30

    for q in questions:
        q_type = q.get('question_type')
        if q_type == 'omr':
            row_centers = []
            x_cursor = CONTENT_LEFT + 60
            for _ in range(5): # A B C D E
                row_centers.append((x_cursor, y_cursor))
                x_cursor += 20
            mcq_bubble_centers.append(row_centers)
            y_cursor -= 25
        elif q_type == 'classical':
            box_width = 60
            box_height = 25
            x_cursor = CONTENT_LEFT + 108
            y_bottom = y_cursor - box_height/2
            classical_score_rects.append((x_cursor, y_bottom, box_width, box_height))
            y_cursor -= 35

    layout['mcq_bubble_centers'] = mcq_bubble_centers
    layout['classical_score_rects'] = classical_score_rects
    layout['omr_count'] = len(mcq_bubble_centers)
    layout['classical_count'] = len(classical_score_rects)

    return layout

def get_student_id_bubble_positions_pdf(layout):
    positions = []
    grid_x = layout.get('student_id_grid_x', CONTENT_LEFT + INFO_COL_WIDTHS[0])
    grid_top = layout.get('student_id_grid_top', BUBBLE_SHEET_TOP - 20)
    spacing_x = layout.get('bubble_spacing_x', BUBBLE_SPACING_X)
    spacing_y = layout.get('bubble_spacing_y', BUBBLE_SPACING_Y)
    radius = layout.get('bubble_radius', BUBBLE_RADIUS)
    length = layout.get('student_id_length', STUDENT_ID_LENGTH)

    start_x = grid_x + 3 + spacing_x/2
    start_y = grid_top - spacing_y/2
    
    for digit_idx in range(length):
        col_cx = start_x + digit_idx * spacing_x
        col_positions = []
        for value in range(10):
            cy = start_y - value * spacing_y
            col_positions.append((col_cx, cy, radius))
        positions.append(col_positions)
    return positions

def get_alignment_marker_centers_warp(layout=None):
    layout = layout or {
        'page_width': PAGE_WIDTH, 'page_height': PAGE_HEIGHT,
        'warp_width': WARP_WIDTH, 'warp_height': WARP_HEIGHT,
    }
    half = MARKER_SIZE / 2
    inset = MARKER_INSET
    page_h = layout.get('page_height', PAGE_HEIGHT)
    page_w = layout.get('page_width', PAGE_WIDTH)
    
    def _pdf_center_to_warp(x_center, y_bottom, lay):
        pw = lay.get('page_width', PAGE_WIDTH)
        ph = lay.get('page_height', PAGE_HEIGHT)
        ow = lay.get('warp_width', WARP_WIDTH)
        oh = lay.get('warp_height', WARP_HEIGHT)
        px = x_center / pw * ow
        py = (1.0 - y_bottom / ph) * oh
        return px, py

    tl = _pdf_center_to_warp(inset + half, page_h - inset - half, layout)
    tr = _pdf_center_to_warp(page_w - inset - half, page_h - inset - half, layout)
    br = _pdf_center_to_warp(page_w - inset - half, inset + half, layout)
    bl = _pdf_center_to_warp(inset + half, inset + half, layout)
    return [tl, tr, br, bl]

def layout_for_exam(exam):
    if exam.sheet_layout:
        return exam.sheet_layout
    omr_count = exam.questions.filter(question_type='omr').count()
    classical_count = exam.questions.filter(question_type='classical').count()
    return compute_sheet_layout(omr_count, classical_count)
