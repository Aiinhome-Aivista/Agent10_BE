"""underwriting.py"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Case, CaseStage, Policy, User

router = APIRouter(prefix="/underwriting", tags=["underwriting"])


class UWDecisionBody(BaseModel):
    policy_id: str
    decision:  str
    remarks:   Optional[str] = None


@router.get("/queue")
async def uw_queue(db: AsyncSession = Depends(get_db),
                   current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    r = await db.execute(select(Case).where(Case.current_stage == CaseStage.UNDERWRITING))
    cases = r.scalars().all()
    return {"queue": [{"id": c.id, "case_number": c.case_number, "sum_assured": c.sum_assured,
                        "stage": str(c.current_stage), "customer_profile": c.customer_profile,
                        "created_at": c.created_at.isoformat() if c.created_at else None}
                       for c in cases]}



@router.post("/decision")
async def uw_decision(body: UWDecisionBody, db: AsyncSession = Depends(get_db),
                       current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    if body.decision not in {"APPROVED", "REJECTED", "DEFERRED"}:
        raise HTTPException(400, "Invalid decision")
    
    r = await db.execute(select(Policy).where(Policy.id == body.policy_id))
    p = r.scalar_one_or_none()
    
    if not p:
        r = await db.execute(select(Policy).where(Policy.case_id == body.policy_id))
        p = r.scalar_one_or_none()
        
    if not p:
        raise HTTPException(404, "Policy or Case not found")

    data = {"uw_status": body.decision, "uw_remarks": body.remarks,
            "uw_reviewed_by": str(current_user.id), "uw_reviewed_at": datetime.utcnow()}
    if body.decision == "APPROVED":
        data["status"] = "APPROVED"
        
    await db.execute(update(Policy).where(Policy.id == p.id).values(**data))
    
    stage = "POLICY_ISSUANCE" if body.decision == "APPROVED" else "EXCEPTION_HANDLING"
    await db.execute(update(Case).where(Case.id == p.case_id).values(current_stage=stage))
    await db.commit()
    return {"message": f"UW decision recorded: {body.decision}"}
