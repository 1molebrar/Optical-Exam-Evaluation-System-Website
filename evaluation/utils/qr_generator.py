"""QR Code Generator for exam papers."""
import json
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile


def generate_qr_data(exam):
    """Generate QR payload with exam identification metadata."""
    layout = exam.get_sheet_layout()
    return json.dumps({
        'exam_id': exam.id,
        'exam_title': exam.title,
        'course_code': exam.course.code,
        'course_name': exam.course.name,
        'omr_count': layout.get('omr_count', 0),
        'classical_count': layout.get('classical_count', 0),
    })


def generate_qr_image(exam):
    """Create QR code image from exam data and return as ContentFile."""
    qr_data = generate_qr_data(exam)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name=f'qr_exam_{exam.id}.png')
