import os
import sys
import django
import cv2
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optical_exam_system.settings')
django.setup()

from evaluation.utils.digit_reader import read_number_from_box, _crop_id_box_interior
from evaluation.utils.image_prep import load_and_warp
from evaluation.utils.layout_engine import compute_sheet_layout
from evaluation.utils.omr import get_classical_score_box_rects

file_path = "media/scanned_papers/KesinLast_7OjVb1F.png"
if os.path.exists(file_path):
    print("Testing OCR on:", file_path)
    prep = load_and_warp(file_path)
    warped = prep['warped']
    layout = compute_sheet_layout()
    rects = get_classical_score_box_rects(layout)
    
    for idx, (x1, y1, x2, y2) in enumerate(rects):
        q_num = idx + 5
        if q_num not in [5, 6, 7, 8]: continue
        x1_shifted = min(warped.shape[1], x1 + 25)
        box_gray = warped[y1:y2, x1_shifted:x2]
        cv2.imwrite(f"debug_q{q_num}_box.png", box_gray)
        
        val, conf, blank = read_number_from_box(box_gray, 100)
        print(f"Q{q_num}: Result={val}, Conf={conf}, Blank={blank}")
else:
    print("File not found.")
