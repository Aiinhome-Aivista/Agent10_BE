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
from backend.app.models.all_models import Case, CaseStage, Policy, User, EscalationLog, WorkflowStageLog

router = APIRouter(prefix="/underwriting", tags=["underwriting"])


class UWDecisionBody(BaseModel):
    policy_id: Optional[str] = None
    case_id: Optional[str] = None
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
    if body.decision not in {"APPROVED", "REJECTED", "DEFERRED", "QUERY"}:
        raise HTTPException(400, "Invalid decision")

    if not body.policy_id and not body.case_id:
        raise HTTPException(400, "policy_id or case_id is required")

    p = None
    case = None
    search_id = body.policy_id or body.case_id

    if body.policy_id:
        r = await db.execute(select(Policy).where(Policy.id == body.policy_id))
        p = r.scalar_one_or_none()
        if not p:
            r = await db.execute(select(Policy).where(Policy.case_id == body.policy_id))
            p = r.scalar_one_or_none()

    if not p and body.case_id:
        r = await db.execute(select(Policy).where(Policy.case_id == body.case_id))
        p = r.scalar_one_or_none()

    if not p:
        r = await db.execute(select(Case).where(Case.id == search_id))
        case = r.scalar_one_or_none()
        if not case:
            raise HTTPException(404, "Policy or Case not found")
    else:
        r = await db.execute(select(Case).where(Case.id == p.case_id))
        case = r.scalar_one_or_none()
        if not case:
            raise HTTPException(404, "Associated case not found for policy")

    if not p and body.decision == "APPROVED":
        raise HTTPException(
            400,
            "No policy draft exists for this case. Create or attach a policy before approving underwriting.",
        )

    if p:
        data = {"uw_status": body.decision, "uw_remarks": body.remarks,
                "uw_reviewed_by": str(current_user.id), "uw_reviewed_at": datetime.utcnow()}
        if body.decision == "APPROVED":
            data["status"] = "APPROVED"
        await db.execute(update(Policy).where(Policy.id == p.id).values(**data))

    # If underwriter raised a query, create an escalation log for the customer to respond
    if body.decision == "QUERY":
        db.add(
            EscalationLog(
                case_id=case.id,
                escalation_level="LEVEL_1",
                stage=str(case.current_stage),
                reason=body.remarks or "Underwriter requested additional information",
                assigned_to_role="CUSTOMER",
                notified=0,
                resolved=0,
            )
        )

    if body.decision == "APPROVED":
        stage = "POLICY_ISSUANCE"
    else:
        stage = "EXCEPTION_HANDLING"

    await db.execute(update(Case).where(Case.id == case.id).values(current_stage=stage))
    await db.commit()
    return {"message": f"UW decision recorded: {body.decision}"}


class QueryResponse(BaseModel):
    message: str


@router.post("/cases/{case_id}/respond-query")
async def respond_query(
    case_id: str,
    body: QueryResponse,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("CUSTOMER", "SUPER_ADMIN")),
):
    # Locate the unresolved EscalationLog for this case
    r = await db.execute(
        select(EscalationLog).where(
            EscalationLog.case_id == case_id,
            EscalationLog.assigned_to_role == "CUSTOMER",
            EscalationLog.resolved == 0,
        )
    )
    esc = r.scalar_one_or_none()
    if not esc:
        raise HTTPException(
            status_code=404,
            detail="No pending underwriting queries found for this case.",
        )

    # Locate the Case
    r_case = await db.execute(select(Case).where(Case.id == case_id))
    case = r_case.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Mark the escalation as resolved
    esc.resolved = 1
    esc.resolved_at = datetime.utcnow()

    # Log customer response in WorkflowStageLog
    old_stage = case.current_stage
    new_stage = CaseStage.UNDERWRITING

    db.add(
        WorkflowStageLog(
            id=str(uuid.uuid4()),
            case_id=case_id,
            from_stage=old_stage.value if hasattr(old_stage, "value") else str(old_stage),
            to_stage=new_stage.value if hasattr(new_stage, "value") else str(new_stage),
            triggered_by=str(current_user.id),
            remarks=body.message,
        )
    )

    # Transition back to UNDERWRITING
    case.current_stage = new_stage
    case.stage_entered_at = datetime.utcnow()
    case.last_activity_at = datetime.utcnow()

    db.add(case)
    db.add(esc)
    await db.commit()

    return {"message": "Response submitted, case returned to underwriting queue."}
