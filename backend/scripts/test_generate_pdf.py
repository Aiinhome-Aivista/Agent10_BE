from datetime import datetime
import os, sys

# Local generate_policy_pdf implementation to avoid importing backend internals
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


def generate_policy_pdf(policy, case):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    uploads_dir = os.path.join(base_dir, 'uploads', 'policies')
    os.makedirs(uploads_dir, exist_ok=True)
    pdf_filename = f"Policy_{policy.policy_number}_{policy.id}.pdf"
    pdf_path = os.path.join(uploads_dir, pdf_filename)

    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#1f2937'), spaceAfter=30, alignment=1)
    story.append(Paragraph("INSURANCE POLICY DOCUMENT", title_style))
    story.append(Spacer(1, 0.2*inch))
    policy_data = [
        ['Policy Number', policy.policy_number or 'N/A'],
        ['Policy ID', policy.id],
        ['Status', policy.status],
        ['Issued Date', policy.issued_at.strftime('%Y-%m-%d') if policy.issued_at else 'N/A'],
        ['Insurer', policy.insurer_name],
        ['Product', policy.product_name],
        ['Sum Assured', f"₹{policy.sum_assured:,.2f}"],
        ['Annual Premium', f"₹{policy.annual_premium:,.2f}"],
        ['Tenure', f"{policy.policy_tenure} years"],
    ]
    t = Table(policy_data, colWidths=[2*inch, 3*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e5e7eb')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle('CustomFooter', parent=styles['Normal'], fontSize=9, textColor=colors.grey, alignment=0)
    story.append(Paragraph("This is an auto-generated policy document. Valid with signature of authorized officer.", footer_style))
    doc.build(story)
    return pdf_path


class DummyPolicy:
    def __init__(self):
        self.id = 'test-policy-1234'
        self.policy_number = 'P-0001'
        self.status = 'ISSUED'
        self.issued_at = datetime.utcnow()
        self.insurer_name = 'ACME Insurance'
        self.product_name = 'Term Cover'
        self.sum_assured = 1000000
        self.annual_premium = 12000
        self.policy_tenure = 10

class DummyCase:
    def __init__(self):
        self.id = 'case-1234'

p = DummyPolicy()
c = DummyCase()

try:
    path = generate_policy_pdf(p, c)
    print('Generated PDF path:', path)
    print('Exists on disk:', os.path.exists(path))
except Exception as e:
    print('Error:', e)
