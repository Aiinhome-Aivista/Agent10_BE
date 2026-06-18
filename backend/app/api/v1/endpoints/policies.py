"""policies.py"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Policy, Quote, Case, User, CaseStage, CaseStatus

router = APIRouter(prefix="/policies", tags=["policies"])


class CreatePolicyBody(BaseModel):
    case_id: str
    quote_id: str


@router.post("/")
async def create_policy(body: CreatePolicyBody, db: AsyncSession = Depends(get_db),
                         current_user=Depends(require_roles("BANKER", "CUSTOMER", "SUPER_ADMIN"))):
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
    return {"policies": [{"id": p.id, "case_id": p.case_id, "policy_number": p.policy_number, "insurer_name": p.insurer_name,
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
    
    # 4. Update policy status to ISSUED
    policy.status = "ISSUED"
    policy.issued_at = datetime.utcnow()
    
    # 5. Update case to COMPLETED
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
        "issued_at": policy.issued_at.isoformat() if policy.issued_at else None
    }


@router.get("/{policy_id}/proposal-pdf")
async def get_proposal_pdf(
    policy_id: str,
    token: str | None = None,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import FileResponse
    from backend.app.repositories.user_repository import UserRepository
    from backend.app.services.pdf_service import generate_proposal_pdf
    from agents.insurer_agents import calculate_age
    from backend.app.core.security import decode_token

    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    # Fetch policy
    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")

    # Fetch case
    cr = await db.execute(select(Case).where(Case.id == policy.case_id))
    case = cr.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Associated case not found")

    # Fetch customer
    customer = await UserRepository(db).get_by_id(policy.customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Fetch quote details
    qr = await db.execute(select(Quote).where(Quote.id == policy.quote_id))
    quote = qr.scalar_one_or_none()

    ai_score = quote.ai_score if (quote and quote.ai_score is not None) else 0.95
    ai_rec = quote.ai_recommendation_text if (quote and quote.ai_recommendation_text) else "Match based on budget and coverage requirements."

    # Prepare pdf parameters
    profile = case.customer_profile or {}
    dob_or_age = profile.get("age") or profile.get("date_of_birth") or profile.get("dob") or 30
    age = calculate_age(str(dob_or_age))
    income = float(profile.get("annual_income") or case.premium_budget or 500000)

    pdf_filename = f"./uploads/proposals/proposal_{policy.id}.pdf"

    generate_proposal_pdf(
        filename=pdf_filename,
        customer_name=customer.name,
        customer_email=customer.email,
        customer_phone=customer.phone,
        customer_age=age,
        customer_income=income,
        insurer_name=policy.insurer_name,
        product_name=policy.product_name,
        premium=policy.annual_premium,
        sum_assured=policy.sum_assured,
        tenure=policy.policy_tenure,
        ai_score=ai_score,
        ai_recommendation=ai_rec,
        summary=case.needs_analysis.get("justification") if case.needs_analysis else ""
    )

    # Save the PDF path to the policy
    policy.policy_document_path = pdf_filename
    db.add(policy)
    await db.commit()

    return FileResponse(
        pdf_filename,
        media_type="application/pdf",
        filename=f"Proposal_{customer.name.replace(' ', '_')}_{policy.insurer_name.replace(' ', '_')}.pdf"
    )
