# Optical Exam Evaluation System

A Django-based system for managing university courses, students, exams, and automated optical exam evaluation using advanced computer vision and OCR on scanned exam papers.

## Project Overview

This system is designed for a university midterm assignment to manage:
- Student registration and management
- Course creation and management
- Student enrollment to courses
- Exam creation with questions (multiple-choice and classical)
- Exam paper generation with optical answer areas and physical alignment markers
- Scanned paper upload and automated processing
- **Advanced OMR (Optical Mark Recognition)** for reading student ID bubble sheets
- **Deep Learning OCR (Optical Character Recognition)** for extracting handwritten scores from classical question boxes
- Interactive evaluation results management and manual review overrides
- JSON data export

## Requirements

- Python 3.8+
- Django 4.2+
- OpenCV (`cv2`)
- EasyOCR
- PyTorch (for EasyOCR backend)
- NumPy, SciPy, Pillow

## Installation

1. **Clone or download the project**

2. **Create a virtual environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Start the development server**:
   ```bash
   python manage.py runserver
   ```

6. **Access the application**:
   Open your browser and navigate to: `http://127.0.0.1:8000/`

## Core Computer Vision Pipeline

The system features a robust, multi-stage image processing pipeline:
1. **Marker Detection & Alignment:** Uses OpenCV contour detection to find 4 corner markers on the scanned paper, calculating a perspective transform matrix to un-warp and align tilted/rotated scans.
2. **OMR (Bubble Sheet) Processing:** Slices the aligned image into the student ID grid, analyzes ink density using thresholding, and decodes the bubbled digits. It maps the 10-digit Student ID (Year, University Code, Department Code, Order).
3. **OCR (Handwritten Digit) Processing:** Extracts classical score boxes based on expected coordinates. Uses Otsu's adaptive thresholding to binarize the handwritten ink, and a hybrid OCR approach (EasyOCR `readtext` with a fallback to `recognize` bypassing CRAFT) to accurately read single and multi-digit handwritten scores.

## Project Structure

```
optical_exam_system/
├── evaluation/
│   ├── utils/
│   │   ├── pipeline.py        # Main computer vision orchestrator
│   │   ├── alignment_refine.py # Perspective alignment & marker detection
│   │   ├── digit_reader.py    # EasyOCR integration & handwritten digit extraction
│   │   └── omr.py             # Bubble sheet ink-density reading (10-digit IDs)
│   ├── migrations/
│   ├── templates/
│   │   ├── index.html
│   │   ├── student_list.html
│   │   ├── student_form.html
│   │   ├── course_list.html
│   │   ├── course_form.html
│   │   ├── exam_list.html
│   │   ├── exam_form.html
│   │   ├── enroll_form.html
│   │   ├── upload_scanned.html
│   │   ├── evaluation_results.html
│   │   ├── evaluation_detail.html
│   │   ├── create_evaluation.html
│   │   └── exam_paper.html
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── media/
│   └── scanned_papers/
├── templates/
├── optical_exam_system/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── manage.py
├── requirements.txt
├── DOCUMENTATION.md
└── README.md
```

## Usage Guide

### 1. Create Students
- Navigate to Students → Add New Student
- Fill in: Student ID (10-digits: YY-UU-DD-NNNN), First Name, Last Name, Email

### 2. Create Universities & Courses
- Navigate to University settings to define University Codes
- Navigate to Courses → Add New Course
- Fill in: Course Code, Name, Description, and assign it to a University/Teacher

### 3. Enroll Students
- Navigate to Enrollment
- Select a student and course to enroll

### 4. Create Exams
- Navigate to Exams → Add New Exam
- Select course, date, duration
- Add questions with marks

### 5. Generate Exam Paper
- Use the exam paper generation feature to create printable papers
- Each paper has a unique code, 4 corner alignment markers, and optical answer bubbles

### 6. Upload Scanned Papers
- After exams are evaluated manually on paper, upload scanned images
- Enter the paper code to link to the correct exam paper

### 7. Process & Evaluate
- The computer vision pipeline will automatically align the paper, read the student ID, and extract handwritten scores via EasyOCR.
- Results with low confidence are flagged with a `Needs Review` status for manual verification.

### 8. Export Results
- Export evaluation results as JSON for further analysis

## Application Routes / Endpoints

| Endpoint | Description |
|----------|-------------|
| `/students/` | List all students |
| `/students/create/` | Create new student |
| `/universities/` | List all universities |
| `/universities/create/` | Create new university |
| `/courses/` | List all courses |
| `/courses/create/` | Create new course |
| `/enroll/` | Enroll student to course |
| `/exams/` | List all exams |
| `/exams/create/` | Create new exam |
| `/exams/<id>/configure/` | Configure questions and answer key |
| `/exam-paper/<id>/` | Generate exam paper for printing |
| `/upload/` | Upload and process scanned paper |
| `/scan-history/` | View history of all scanned uploads |
| `/reviews/` | Manual review dashboard for low-confidence scans |
| `/results/` | View all evaluation results |
| `/results/export/<id>/` | Export results as CSV |
| `/results/export/<id>/json/` | Export results as JSON |

## Models

1. **University** - University definitions and codes
2. **Student** - Student information (10-digit mapped ID)
3. **Course** - Course details (Linked to University and Teacher)
4. **Enrollment** - Student-Course relationship
5. **Exam** - Exam details
6. **Question** - Exam questions
7. **ExamPaper** - Generated exam paper for student
8. **ScannedPaper** - Uploaded scanned image
9. **EvaluationResult** - Evaluation outcome
10. **QuestionScore** - Individual question scores

## Technology Stack

- **Backend**: Django 4.2+
- **Database**: SQLite (default)
- **Computer Vision**: OpenCV (cv2), NumPy
- **OCR Engine**: EasyOCR, PyTorch
- **Frontend**: HTML, Bootstrap 5, Vanilla CSS

## License

This project is for educational purposes.

## Author

University Midterm Assignment - Optical Exam Evaluation System
