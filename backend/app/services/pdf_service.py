import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_proposal_pdf(
    filename: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    customer_age: int,
    customer_income: float,
    insurer_name: str,
    product_name: str,
    premium: float,
    sum_assured: float,
    tenure: int,
    ai_score: float,
    ai_recommendation: str,
    summary: str
):
    # Ensure target directory exists
    target_dir = os.path.dirname(filename)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)
        
    doc = SimpleDocTemplate(
        filename, 
        pagesize=letter, 
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    story = []
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#1e1b4b'),
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#4f46e5'),
        spaceAfter=20
    )
    
    section_title = ParagraphStyle(
        'SecTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=6
    )
    
    bold_body = ParagraphStyle(
        'BoldBody',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    
    recommendation_box = ParagraphStyle(
        'RecBox',
        parent=body_style,
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#0d9488')
    )

    # Header section
    story.append(Paragraph("BANCASSURANCE PROPOSAL SUMMARY", title_style))
    story.append(Paragraph("Suggestive AI Insurance Matching Report", subtitle_style))
    story.append(Spacer(1, 10))
    
    # Table 1: Customer Profile
    story.append(Paragraph("1. Customer Profile", section_title))
    cust_data = [
        [Paragraph("Customer Name:", bold_body), Paragraph(customer_name, body_style),
         Paragraph("Age:", bold_body), Paragraph(str(customer_age), body_style)],
        [Paragraph("Email:", bold_body), Paragraph(customer_email, body_style),
         Paragraph("Phone:", bold_body), Paragraph(customer_phone or "—", body_style)],
        [Paragraph("Annual Income:", bold_body), Paragraph(f"INR {customer_income:,.2f}", body_style),
         Paragraph("", bold_body), Paragraph("", body_style)]
    ]
    t_cust = Table(cust_data, colWidths=[110, 150, 110, 150])
    t_cust.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_cust)
    story.append(Spacer(1, 15))
    
    # Table 2: Policy Details
    story.append(Paragraph("2. Selected Insurance Product Details", section_title))
    policy_data = [
        [Paragraph("Insurer Name:", bold_body), Paragraph(insurer_name, body_style),
         Paragraph("Plan Name:", bold_body), Paragraph(product_name, body_style)],
        [Paragraph("Sum Assured:", bold_body), Paragraph(f"INR {sum_assured:,.2f}", body_style),
         Paragraph("Annual Premium:", bold_body), Paragraph(f"INR {premium:,.2f}", body_style)],
        [Paragraph("Policy Tenure:", bold_body), Paragraph(f"{tenure} Years", body_style),
         Paragraph("AI Match Score:", bold_body), Paragraph(f"{int(ai_score * 100)}% Match", bold_body)]
    ]
    t_policy = Table(policy_data, colWidths=[110, 150, 110, 150])
    t_policy.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#bbf7d0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dcfce7')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_policy)
    story.append(Spacer(1, 15))
    
    # AI Justification Box
    story.append(Paragraph("3. AI Recommendation & Justification", section_title))
    rec_html = f"<strong>Why this policy is recommended for you:</strong><br/>{ai_recommendation}"
    p_rec = Paragraph(rec_html, recommendation_box)
    
    t_rec = Table([[p_rec]], colWidths=[520])
    t_rec.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ccfbf1')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#99f6e4')),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t_rec)
    story.append(Spacer(1, 15))
    
    # Final Summary / Details
    story.append(Paragraph("4. Summary & Next Steps", section_title))
    summary_text = summary or "This is a preliminary proposal draft. Standard underwriting rules apply. Please proceed with e-KYC and signature options to submit to the insurer."
    story.append(Paragraph(summary_text, body_style))
    
    story.append(Spacer(1, 30))
    story.append(Paragraph("Thank you for using Bancassurance Suggestive AI Agent.", subtitle_style))
    
    doc.build(story)
