"""policies.py"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles, decode_token
from backend.app.models.all_models import Policy, Quote, Case, User, CaseStage, CaseStatus
from backend.app.repositories.user_repository import UserRepository

import os
from fastapi.responses import FileResponse

router = APIRouter(prefix="/policies", tags=["policies"])

def generate_policy_pdf(policy, case):
    """Generate PDF for policy document"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
    except Exception:
        raise RuntimeError("reportlab is required for PDF generation. Install with: pip install reportlab")
    # Resolve absolute uploads directory under the backend root so paths are consistent
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    uploads_dir = os.path.join(base_dir, 'uploads', 'policies')
    os.makedirs(uploads_dir, exist_ok=True)

    # Generate filename
    pdf_filename = f"Policy_{policy.policy_number}_{policy.id}.pdf"
    pdf_path = os.path.join(uploads_dir, pdf_filename)
    
    # Create PDF
    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=30,
        alignment=1
    )
    
    # Add title
    story.append(Paragraph("INSURANCE POLICY DOCUMENT", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Policy details table
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
    
    # Footer text
    footer_style = ParagraphStyle(
        'CustomFooter',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=0
    )
    story.append(Paragraph("This is an auto-generated policy document. Valid with signature of authorized officer.", footer_style))
    
    # Build PDF
    doc.build(story)
    return pdf_path

class CreatePolicyBody(BaseModel):
    case_id: str
    quote_id: str


@router.post("/")
async def create_policy(body: CreatePolicyBody, db: AsyncSession = Depends(get_db),
                         current_user=Depends(require_roles("BANKER", "SUPER_ADMIN"))):
    r = await db.execute(select(Case).where(Case.id == body.case_id))
    case = r.scalar_one_or_none()
    if not case: raise HTTPException(404, "Case not found")
    qr = await db.execute(select(Quote).where(Quote.id == body.quote_id))
    q = qr.scalar_one_or_none()
    if not q: raise HTTPException(404, "Quote not found")
    existing = await db.execute(select(Policy).where(Policy.case_id == body.case_id))
    if existing.scalar_one_or_none(): raise HTTPException(409, "Policy already exists")
    policy = Policy(
        id=str(uuid.uuid4()), case_id=body.case_id, quote_id=body.quote_id,
        customer_id=case.customer_id, insurer_code=q.insurer_code, insurer_name=q.insurer_name,
        product_name=q.product_name, product_code=q.product_code,
        annual_premium=q.annual_premium, sum_assured=q.sum_assured, policy_tenure=q.policy_tenure,
    )
    db.add(policy); await db.commit(); await db.refresh(policy)
    return {"policy_id": policy.id, "message": "Policy draft created"}


@router.get("/customer/{customer_id}")
async def customer_policies(customer_id: str, db: AsyncSession = Depends(get_db),
                              current_user=Depends(get_current_user)):
    r = await db.execute(select(Policy).where(Policy.customer_id == customer_id).order_by(Policy.created_at.desc()))
    policies = r.scalars().all()
    return {"policies": [{"id": p.id, "policy_number": p.policy_number, "insurer_name": p.insurer_name,
                           "product_name": p.product_name, "annual_premium": p.annual_premium,
                           "sum_assured": p.sum_assured, "status": p.status,
                           "created_at": p.created_at.isoformat() if p.created_at else None} for p in policies]}


@router.get("/")
async def all_policies(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db),
                        current_user=Depends(require_roles("SUPER_ADMIN", "UNDERWRITER"))):
    r = await db.execute(select(Policy).order_by(Policy.created_at.desc()).offset(skip).limit(limit))
    policies = r.scalars().all()
    return {"policies": [{"id": p.id, "case_id": p.case_id, "policy_number": p.policy_number,
                           "insurer_name": p.insurer_name, "sum_assured": p.sum_assured,
                           "status": p.status} for p in policies]}


@router.post("/{policy_id}/issue")
async def issue_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("SUPER_ADMIN", "UNDERWRITER"))
):
    """Issue a policy and transition case to COMPLETED stage"""
    # 1. Find and validate policy
    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    # 2. Find associated case
    cr = await db.execute(select(Case).where(Case.id == policy.case_id))
    case = cr.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Associated case not found")
    
    # 3. Validate policy is in POLICY_ISSUANCE stage
    if case.current_stage != CaseStage.POLICY_ISSUANCE:
        raise HTTPException(
            400,
            f"Policy can only be issued from POLICY_ISSUANCE stage. Current stage: {case.current_stage}"
        )
    
    # 4. Generate policy PDF
    pdf_path = generate_policy_pdf(policy, case)
    policy.policy_document_path = pdf_path
    
    # 5. Update policy status to ISSUED
    policy.status = "ISSUED"
    policy.issued_at = datetime.utcnow()
    
    # 6. Update case to COMPLETED
    await db.execute(
        update(Case)
        .where(Case.id == policy.case_id)
        .values(
            current_stage=CaseStage.COMPLETED,
            status=CaseStatus.COMPLETED,
            last_activity_at=datetime.utcnow()
        )
    )
    
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    
    return {
        "message": "Policy issued successfully",
        "policy_id": policy.id,
        "case_id": policy.case_id,
        "policy_status": policy.status,
        "policy_document_path": pdf_path,
        "issued_at": policy.issued_at.isoformat() if policy.issued_at else None
    }


@router.post("/{policy_id}/regenerate")
async def regenerate_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("SUPER_ADMIN", "UNDERWRITER"))
):
    """Regenerate policy PDF document on demand and save path to policy."""
    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    # Fetch case for context
    cr = await db.execute(select(Case).where(Case.id == policy.case_id))
    case = cr.scalar_one_or_none()
    # Generate PDF
    try:
        pdf_path = generate_policy_pdf(policy, case)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    policy.policy_document_path = pdf_path
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return {"policy_document_path": pdf_path}


@router.get("/{policy_id}/download")
async def download_policy(
    policy_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Download policy PDF document"""
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ", 1)[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    if not policy.policy_document_path:
        raise HTTPException(404, "Policy document not yet generated")
    
    if not os.path.exists(policy.policy_document_path):
        raise HTTPException(404, "Policy document file not found on server")
    
    filename = f"Policy_{policy.policy_number}_{policy.id}.pdf" if policy.policy_number else f"Policy_{policy.id}.pdf"
    
    return FileResponse(
        policy.policy_document_path,
        media_type="application/pdf",
        filename=filename
    )
