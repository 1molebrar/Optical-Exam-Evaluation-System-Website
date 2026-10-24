import os
import json
from django.core.management.base import BaseCommand
from evaluation.models import ScannedPaper, ExamPaper, Student, Exam, ExamResult
from evaluation.utils.pipeline import process_scanned_paper, grade_answers
from evaluation.utils.matching import (
    match_exam_from_qr, match_student_from_ocr, can_auto_finalize_scan, normalize_student_id,
)


class Command(BaseCommand):
    help = 'Re-process existing scanned papers with updated OMR/OCR logic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Re-process ALL scanned papers',
        )
        parser.add_argument(
            '--id',
            type=int,
            default=None,
            help='Re-process a specific scanned paper by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        if options['id'] is not None:
            papers = ScannedPaper.objects.filter(id=options['id'])
        elif options['all']:
            papers = ScannedPaper.objects.all()
        else:
            # Default: only process papers with missing exam/student
            papers = ScannedPaper.objects.filter(
                matched_exam__isnull=True
            ) | ScannedPaper.objects.filter(
                matched_student__isnull=True
            )
            papers = papers.distinct()

        self.stdout.write(f'Found {papers.count()} papers to process')

        count = 0
        updated = 0

        for scanned in papers:
            count += 1
            path = scanned.image.path
            exists = os.path.isfile(path)

            if not exists:
                self.stdout.write(self.style.WARNING(f'  [{count}] ID={scanned.id}: File missing - skipping'))
                continue

            self.stdout.write(f'  [{count}] ID={scanned.id}: {scanned.image.name}')

            qr = {}
            try:
                from evaluation.utils.qr_reader import read_qr_from_image
                qr = read_qr_from_image(path)
            except Exception:
                pass

            matched_exam = match_exam_from_qr(qr) or scanned.matched_exam
            if matched_exam:
                matched_exam.refresh_sheet_layout()

            result = process_scanned_paper(path, exam=matched_exam)

            if options['verbose']:
                self.stdout.write(f'       QR: exam_id={result["qr"]["exam_id"]}, err={result["qr"]["error"]}')
                self.stdout.write(f'       OCR: student_id={result["ocr"]["student_id"]!r}, conf={result["ocr"]["confidence"]}')
                self.stdout.write(f'       OMR: {len(result["omr"]["answers"])} answers')
                self.stdout.write(f'       needs_review={result["needs_review"]}')

            if options['dry_run']:
                continue

            # Update scanned paper with new data
            qr = result['qr']
            ocr = result['ocr']
            omr = result['omr']
            ocr_scores = result.get('ocr_scores', {}).get('scores', [])
            omr_answers = omr.get('answers', [])

            # Combine all answers
            all_answers = list(omr_answers)
            for s in ocr_scores:
                all_answers.append({
                    'question_number': s['question_number'],
                    'detected': str(s.get('detected_score', 0)),
                    'is_blank': s.get('is_blank', True),
                    'needs_review': s.get('needs_review', False),
                    'exceeds_max': s.get('exceeds_max', False),
                    'section': 'Classical',
                    'question_type': 'classical',
                })

            # Update fields
            scanned.qr_data = json.dumps(qr)
            scanned.qr_success = not qr['needs_review']
            scanned.qr_confidence = 80.0 if not qr['needs_review'] else 0.0
            scanned.ocr_student_id = normalize_student_id(ocr.get('student_id', ''))
            scanned.ocr_confidence = ocr.get('confidence', 0.0)
            scanned.omr_confidence = omr.get('confidence', 0.0)
            scanned.detected_answers = json.dumps(all_answers)

            scanned.matched_exam = match_exam_from_qr(qr)
            scanned.matched_student = result.get('matched_student') or match_student_from_ocr(scanned.ocr_student_id)

            if scanned.matched_exam:
                grading = grade_answers(
                    omr_answers,
                    scanned.matched_exam,
                    scanned.ocr_student_id or 'UNKNOWN',
                    ocr_scores=ocr_scores,
                )

                if can_auto_finalize_scan(scanned):
                    from evaluation.views import finalize_scanned_result
                    finalize_scanned_result(scanned, grading, all_answers)
                    scanned.status = 'completed'
                    scanned.needs_review = False
                else:
                    scanned.needs_review = True
                    scanned.status = 'needs_review'
            else:
                scanned.needs_review = True
                scanned.status = 'needs_review'

            scanned.processed = True
            scanned.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(f'Done: {count} papers processed, {updated} updated'))
