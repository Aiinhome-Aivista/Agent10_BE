"""policies.py"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Policy, Quote, Case, User

router = APIRouter(prefix="/policies", tags=["policies"])


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
                        current_user=Depends(require_roles("SUPER_ADMIN", "COMPLIANCE"))):
    r = await db.execute(select(Policy).order_by(Policy.created_at.desc()).offset(skip).limit(limit))
    policies = r.scalars().all()
    return {"policies": [{"id": p.id, "case_id": p.case_id, "policy_number": p.policy_number,
                           "insurer_name": p.insurer_name, "sum_assured": p.sum_assured,
                           "status": p.status} for p in policies]}
