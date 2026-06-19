"""Service for generating Policy PDF documents using reportlab."""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def get_profile_val(d: dict, key_name: str, default: str = 'N/A') -> str:
    """Helper to retrieve values from customer profile case-insensitively."""
    if not isinstance(d, dict):
        return default
    # Clean key name
    target = key_name.lower().replace(" ", "").replace("_", "").replace("-", "")
    for k, v in d.items():
        clean_k = k.lower().replace(" ", "").replace("_", "").replace("-", "")
        if clean_k == target:
            if v is None:
                return default
            return str(v)
    return default

def generate_policy_pdf(policy, customer_profile: dict, save_dir: str) -> str:
    """Generate a PDF for the issued policy and return the saved file path.
    
    Args:
        policy: The Policy model instance.
        customer_profile: Dict containing customer profile details.
        save_dir: Path to directory where file should be saved.
    """
    os.makedirs(save_dir, exist_ok=True)
    filename = f"policy_{policy.policy_number or policy.id}.pdf"
    save_path = os.path.join(save_dir, filename)
    
    # 1. Page setup - 0.75 in margins (54 points)
    doc = SimpleDocTemplate(
        save_path, 
        pagesize=letter, 
        rightMargin=54, 
        leftMargin=54, 
        topMargin=54, 
        bottomMargin=54
    )
    
    story = []
    
    # 2. Get and create styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#4f46e5'), # Tailwind Indigo 600
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#6b7280'), # Gray 500
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#111827'), # Gray 900
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#374151') # Gray 700
    )
    
    footer_style = ParagraphStyle(
        'FooterText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#9ca3af'), # Gray 400
        alignment=1 # Center aligned
    )

    # 3. Build Header Card / Title
    story.append(Paragraph("Q2P Insurance Platform", title_style))
    story.append(Paragraph(f"Official Policy Bond - Policy Number: {policy.policy_number or 'Draft/Pending'}", subtitle_style))
    story.append(Spacer(1, 10))
    
    # Dates formatting
    issued_str = policy.issued_at.strftime('%d-%b-%Y') if policy.issued_at else datetime.utcnow().strftime('%d-%b-%Y')
    commence_str = policy.commencement_date.strftime('%d-%b-%Y') if policy.commencement_date else issued_str
    valid_str = policy.maturity_date.strftime('%d-%b-%Y') if policy.maturity_date else 'N/A'

    # 4. Policy details table
    data = [
        [Paragraph("<b>Policy Parameter</b>", body_style), Paragraph("<b>Details</b>", body_style)],
        [Paragraph("Insurer Name", body_style), Paragraph(policy.insurer_name or "N/A", body_style)],
        [Paragraph("Product Name", body_style), Paragraph(policy.product_name or "N/A", body_style)],
        [Paragraph("Sum Assured", body_style), Paragraph(f"INR {policy.sum_assured:,.2f}" if policy.sum_assured else "N/A", body_style)],
        [Paragraph("Annual Premium", body_style), Paragraph(f"INR {policy.annual_premium:,.2f}" if policy.annual_premium else "N/A", body_style)],
        [Paragraph("Policy Tenure", body_style), Paragraph(f"{policy.policy_tenure} Years" if policy.policy_tenure else "N/A", body_style)],
        [Paragraph("Premium Frequency", body_style), Paragraph(str(policy.premium_frequency or "ANNUAL"), body_style)],
        [Paragraph("Status", body_style), Paragraph(policy.status.value if hasattr(policy.status, 'value') else str(policy.status), body_style)],
        [Paragraph("Commencement Date", body_style), Paragraph(commence_str, body_style)],
        [Paragraph("Valid Upto", body_style), Paragraph(valid_str, body_style)],
        [Paragraph("Issued At", body_style), Paragraph(issued_str, body_style)]
    ]
    
    t = Table(data, colWidths=[200, 304])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e5e7eb')), # gray-300 header
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')), # gray-400 grid lines
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    
    story.append(Paragraph("1. Policy Details", h2_style))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Retrieve demographics case-insensitively
    gender_val = get_profile_val(customer_profile, 'gender')
    occupation_val = get_profile_val(customer_profile, 'occupation')
    dob_val = get_profile_val(customer_profile, 'dateofbirth')
    if dob_val == 'N/A':
        dob_val = get_profile_val(customer_profile, 'dob')
    
    # 5. Customer details
    cust_data = [
        [Paragraph("<b>Customer Detail</b>", body_style), Paragraph("<b>Information</b>", body_style)],
        [Paragraph("Full Name", body_style), Paragraph(get_profile_val(customer_profile, 'name'), body_style)],
        [Paragraph("Email Address", body_style), Paragraph(get_profile_val(customer_profile, 'email'), body_style)],
        [Paragraph("Phone Number", body_style), Paragraph(get_profile_val(customer_profile, 'phone'), body_style)],
        [Paragraph("Date of Birth", body_style), Paragraph(dob_val, body_style)],
        [Paragraph("Gender", body_style), Paragraph(gender_val, body_style)],
        [Paragraph("Occupation", body_style), Paragraph(occupation_val, body_style)]
    ]
    
    t_cust = Table(cust_data, colWidths=[200, 304])
    t_cust.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e5e7eb')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    
    story.append(Paragraph("2. Insured Profile", h2_style))
    story.append(t_cust)
    story.append(Spacer(1, 25))
    
    # 6. Disclaimer & Signatures
    story.append(Paragraph("This is an electronically generated policy document. It is verified and signed using the Q2P Platform. Underwriter approval has been granted digitally.", footer_style))
    story.append(Paragraph("For support or queries, contact the issuing insurer or Q2P Customer Service.", footer_style))
    
    doc.build(story)
    return save_path
