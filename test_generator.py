import sys
import os
sys.path.insert(0, os.path.abspath('..'))

from evaluation.utils.paper_generator import generate_exam_pdf

class MockCourse:
    code = "FET342"
    name = "Sunucu Taraflı Web Programlama"

class MockExam:
    id = 1
    course = MockCourse()
    title = "Sunucu Taraflı Web Programlama"
    exam_date = None

class MockExamPaper:
    exam = MockExam()
    paper_code = "ABC123XY"
    qr_image = None

exam = MockExam()
paper = MockExamPaper()

pdf_buffer = generate_exam_pdf(exam, paper)
with open("test_output2.pdf", "wb") as f:
    f.write(pdf_buffer.read())

print("PDF generated")
