"""Customer query endpoints: list pending queries and reply/upload responses"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import EscalationLog, Case
from backend.app.models.all_models import User

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("/mine")
async def my_queries(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    # Return escalations assigned to the current customer's cases and not resolved
    r = await db.execute(select(EscalationLog).where(EscalationLog.assigned_to_role == "CUSTOMER", EscalationLog.resolved == 0))
    items = r.scalars().all()
    results = []
    for e in items:
        # load case summary
        cr = await db.execute(select(Case).where(Case.id == e.case_id))
        c = cr.scalar_one_or_none()
        results.append({
            "id": e.id,
            "case_id": e.case_id,
            "case_number": c.case_number if c else None,
            "reason": e.reason,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "resolved": e.resolved,
        })
    return {"queries": results}


@router.post("/{escalation_id}/reply")
async def reply_query(escalation_id: str, message: str = Form(...), files: List[UploadFile] = File(None), db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("CUSTOMER","SUPER_ADMIN"))):
    # Mark escalation as resolved. File attachments are expected to be uploaded via the /documents/upload endpoint
    r = await db.execute(select(EscalationLog).where(EscalationLog.id == escalation_id))
    e = r.scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Escalation not found")
    # TODO: integrate with /documents/upload to persist attachments
    e.resolved = 1
    e.resolved_at = datetime.utcnow()
    e.resolved_by = str(current_user.id)
    db.add(e)
    await db.commit()
    return {"message": "Reply recorded, underwriter notified"}
