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
from backend.app.models.all_models import Case, CaseStage, Policy, User, EscalationLog, MedicalRequest, KycDocument

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
                        "current_stage": str(c.current_stage), "kyc_status": c.kyc_status,
                        "customer_profile": c.customer_profile,
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
    return {"message": f"UW decision recorded: {body.decision}"}


async def _refresh_case_kyc_status(db: AsyncSession, case_id: str):
    r = await db.execute(select(KycDocument).where(KycDocument.case_id == case_id))
    docs = r.scalars().all()
    statuses = {d.status for d in docs}
    if not docs:
        overall = "PENDING"
    elif "REJECTED" in statuses:
        overall = "REJECTED"
    elif statuses == {"APPROVED"}:
        overall = "APPROVED"
    elif "UNDER_REVIEW" in statuses or "PENDING" in statuses:
        overall = "UNDER_REVIEW"
    else:
        overall = "PENDING"
    await db.execute(update(Case).where(Case.id == case_id).values(kyc_status=overall))
    return overall


@router.get("/case/{case_id}/documents")
async def get_case_kyc_documents(case_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    r = await db.execute(select(KycDocument).where(KycDocument.case_id == case_id))
    docs = r.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "case_id": d.case_id,
                "customer_id": d.customer_id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "status": d.status,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                "verified_by": d.verified_by,
                "verifier_remarks": d.verifier_remarks,
                "view_url": f"/api/v1/kyc/{d.id}/view",
            }
            for d in docs
        ]
    }


class UnderwriterDocumentActionBody(BaseModel):
    document_id: str
    remarks: Optional[str] = None


@router.post("/document/approve")
async def approve_document(body: UnderwriterDocumentActionBody, db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    r = await db.execute(select(KycDocument).where(KycDocument.id == body.document_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.execute(
        update(KycDocument)
        .where(KycDocument.id == body.document_id)
        .values(status="APPROVED", verified_by=str(current_user.id), verifier_remarks=body.remarks)
    )
    overall = await _refresh_case_kyc_status(db, doc.case_id)
    await db.commit()
    return {"message": "Document approved", "overall_status": overall}


@router.post("/document/reject")
async def reject_document(body: UnderwriterDocumentActionBody, db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    r = await db.execute(select(KycDocument).where(KycDocument.id == body.document_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.execute(
        update(KycDocument)
        .where(KycDocument.id == body.document_id)
        .values(status="REJECTED", verified_by=str(current_user.id), verifier_remarks=body.remarks)
    )
    overall = await _refresh_case_kyc_status(db, doc.case_id)
    await db.commit()
    return {"message": "Document rejected", "overall_status": overall}


class UnderwriterQueryBody(BaseModel):
    case_id: str
    remarks: Optional[str] = None
    requirements: Optional[list[str]] = None


@router.post("/query")
async def raise_underwriter_query(body: UnderwriterQueryBody, db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("UNDERWRITER", "SUPER_ADMIN"))):
    result = await db.execute(select(Case).where(Case.id == body.case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    message = body.remarks or "Underwriter requested additional information"
    requirements = body.requirements or [message]
    db.add(
        EscalationLog(
            case_id=case.id,
            escalation_level="LEVEL_1",
            stage=str(case.current_stage),
            reason=message,
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
            requirements=requirements,
            status="PENDING",
            ops_remarks="Underwriter raised query",
        )
    )
    await db.execute(update(Case).where(Case.id == case.id).values(current_stage=CaseStage.MEDICAL_COORDINATION, kyc_status="UNDER_REVIEW"))
    await db.commit()
    return {"message": "Query raised", "requirements": requirements}
