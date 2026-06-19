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
from backend.app.models.all_models import Case, CaseStage, Policy, User, EscalationLog, MedicalRequest

router = APIRouter(prefix="/underwriting", tags=["underwriting"])


class UWDecisionBody(BaseModel):
    policy_id: Optional[str] = None
    case_id: Optional[str] = None
    decision:  str
    remarks:   Optional[str] = None


@router.get("/queue")
async def uw_queue(db: AsyncSession = Depends(get_db),
                   current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    r = await db.execute(
        select(Case).where(
            Case.current_stage.in_([
                CaseStage.PROPOSAL_GENERATION,
                CaseStage.MEDICAL_COORDINATION,
                CaseStage.UNDERWRITING,
            ])
        )
    )
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

    from backend.app.services.notification_service import create_in_app_notification

    # If underwriter raised a query, create an escalation log and a medical request
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
        db.add(
            MedicalRequest(
                id=str(uuid.uuid4()),
                case_id=case.id,
                customer_id=case.customer_id,
                requirements=[body.remarks or "QUERY_RESPONSE"],
                status="PENDING",
                ops_remarks="Underwriter raised query",
            )
        )

    if body.decision == "APPROVED":
        stage = CaseStage.POLICY_ISSUANCE
    elif body.decision == "QUERY":
        stage = CaseStage.MEDICAL_COORDINATION
    else:
        stage = CaseStage.EXCEPTION_HANDLING

    await db.execute(update(Case).where(Case.id == case.id).values(current_stage=stage))
    await db.commit()

    # Retrieve customer & banker details to notify
    customer_res = await db.execute(select(User).where(User.id == case.customer_id))
    customer = customer_res.scalar_one_or_none()
    banker_res = await db.execute(select(User).where(User.id == case.banker_id))
    banker = banker_res.scalar_one_or_none()

    if body.decision == "QUERY" and customer:
        await create_in_app_notification(
            db,
            recipient_id=customer.id,
            recipient_email=customer.email,
            subject="KYC & Medical Documents Required",
            body=f"Underwriter has requested additional documents or information for Case {case.case_number}: {body.remarks or 'Please upload requested documents.'}",
            reference_id=case.id,
        )
        if banker:
            await create_in_app_notification(
                db,
                recipient_id=banker.id,
                recipient_email=banker.email,
                subject="Underwriter Raised Query",
                body=f"Underwriter has raised a query or requested documents for Case {case.case_number}.",
                reference_id=case.id,
            )
    elif body.decision == "APPROVED" and banker:
        await create_in_app_notification(
            db,
            recipient_id=banker.id,
            recipient_email=banker.email,
            subject="Underwriting Approved",
            body=f"Underwriting has been approved for Case {case.case_number}. Ready for policy issuance.",
            reference_id=case.id,
        )
        if customer:
            await create_in_app_notification(
                db,
                recipient_id=customer.id,
                recipient_email=customer.email,
                subject="Underwriting Approved",
                body=f"Your underwriting review has been approved for Case {case.case_number}. Ready for policy issuance.",
                reference_id=case.id,
            )

    return {"message": f"UW decision recorded: {body.decision}"}
