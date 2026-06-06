"""compliance.py"""
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import require_roles
from backend.app.models.all_models import Policy, ConsentRecord

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/dashboard")
async def compliance_dashboard(db: AsyncSession = Depends(get_db),
                                current_user=Depends(require_roles("COMPLIANCE", "SUPER_ADMIN"))):
    r = await db.execute(select(Policy))
    policies = r.scalars().all()
    total   = len(policies)
    checked = sum(1 for p in policies if p.compliance_checked)
    score   = round(checked / total * 100, 1) if total else 0
    return {"compliance_score": score, "total_policies": total, "checked": checked,
            "exceptions": sum(1 for p in policies if p.compliance_remarks)}


@router.get("/exceptions")
async def exceptions(db: AsyncSession = Depends(get_db),
                     current_user=Depends(require_roles("COMPLIANCE", "SUPER_ADMIN"))):
    r = await db.execute(select(Policy).where(Policy.compliance_remarks.isnot(None)))
    policies = r.scalars().all()
    return {"exceptions": [{"id": p.id, "case_id": p.case_id, "policy_number": p.policy_number,
                             "status": p.status, "compliance_remarks": p.compliance_remarks} for p in policies]}


@router.get("/consents")
async def consents(db: AsyncSession = Depends(get_db),
                   current_user=Depends(require_roles("COMPLIANCE", "SUPER_ADMIN"))):
    r = await db.execute(select(ConsentRecord).order_by(ConsentRecord.consented_at.desc()).limit(100))
    records = r.scalars().all()
    return {"consents": [{"id": c.id, "case_id": c.case_id, "customer_id": c.customer_id,
                           "consent_type": c.consent_type,
                           "consented_at": c.consented_at.isoformat() if c.consented_at else None} for c in records]}


class UpdateComplianceBody(BaseModel):
    compliance_checked: bool
    compliance_remarks: Optional[str] = None


@router.patch("/policy/{policy_id}")
async def update_compliance(policy_id: str, body: UpdateComplianceBody,
                             db: AsyncSession = Depends(get_db),
                             current_user=Depends(require_roles("COMPLIANCE", "SUPER_ADMIN"))):
    await db.execute(update(Policy).where(Policy.id == policy_id).values(
        compliance_checked=int(body.compliance_checked),
        compliance_remarks=body.compliance_remarks,
    ))
    await db.commit()
    return {"message": "Compliance updated"}
