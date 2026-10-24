import sys
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4
MARKER_SIZE = 15
MARKER_INSET = 30

def draw_alignment_markers(c, page_width, page_height):
    corners = [
        (MARKER_INSET, page_height - MARKER_INSET - MARKER_SIZE),
        (page_width - MARKER_INSET - MARKER_SIZE, page_height - MARKER_INSET - MARKER_SIZE),
        (page_width - MARKER_INSET - MARKER_SIZE, MARKER_INSET),
        (MARKER_INSET, MARKER_INSET),
    ]
    for cx, cy in corners:
        c.setFillColor(black)
        c.rect(cx, cy, MARKER_SIZE, MARKER_SIZE, fill=1, stroke=0)

def draw_pdf():
    c = canvas.Canvas('test_output.pdf', pagesize=A4)
    draw_alignment_markers(c, PAGE_WIDTH, PAGE_HEIGHT)
    
    # logo area
    # ...
    
    c.save()

if __name__ == '__main__':
    draw_pdf()
    print("PDF generated successfully")
