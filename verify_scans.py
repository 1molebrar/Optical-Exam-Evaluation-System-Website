import os
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optical_exam_system.settings')
django.setup()

from evaluation.models import ExamResult, ScannedPaper
from evaluation.utils import image_prep
from evaluation.utils.paper_layout import get_classical_score_box_rects
from evaluation.utils.digit_reader import read_number_from_box

EXPECTED = {
    34: {6: 9, 7: 8, 8: 7, 9: 6, 10: 5},
    35: {6: 10, 7: 1, 8: 0, 9: 15, 10: 3},
}

for sid in (34, 35):
    p = ScannedPaper.objects.get(id=sid)
    r = ExamResult.objects.filter(scanned_paper=p).first()
    print(f'=== scan {sid} status={p.status} review={p.needs_review} ===')
    if r:
        print(f'score {float(r.earned_points)}/{float(r.total_points)} = {float(r.score)}%')
        for a in json.loads(r.answers):
            exceeds = a.get('exceeds_max')
            print(
                f"  Q{a['question_number']:>2} "
                f"{'OMR' if a.get('question_type')=='omr' else 'CLS'} "
                f"correct={a.get('correct_answer')} "
                f"got={a.get('detected')} "
                f"earned={float(a.get('earned_points', 0))} "
                f"exceeds={exceeds}"
            )

    layout = p.matched_exam.get_sheet_layout()
    warped = image_prep.load_and_warp(p.image.path)['warped']
    print('  classical OCR check:')
    for q, exp in EXPECTED[sid].items():
        rect = get_classical_score_box_rects(layout)[q - 6]
        box = warped[rect[1]:rect[3], rect[0]:rect[2]]
        got = read_number_from_box(box)[0]
        ok = 'OK' if got == exp else 'MISS'
        print(f'    Q{q} exp={exp} got={got} {ok}')
