import uuid, os, logging
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import MedicalRequest, MedicalDocument, User, Case, CaseStage
from configs.base import settings

router = APIRouter(prefix="/medical", tags=["medical"])
logger = logging.getLogger(__name__)


@router.get("/cases-for-uw")
async def cases_for_uw(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("OPS_ADMIN", "UNDERWRITER", "SUPER_ADMIN")),
):
    """Return all cases in PROPOSAL_GENERATION, MEDICAL_COORDINATION, or UNDERWRITING stages."""
    from backend.app.models.all_models import Quote
    result = await db.execute(
        select(Case)
        .where(Case.current_stage.in_([
            CaseStage.OTP_CONSENT,
            CaseStage.PROPOSAL_GENERATION,
            CaseStage.MEDICAL_COORDINATION,
            CaseStage.UNDERWRITING,
        ]))
        .order_by(Case.created_at.desc())
    )
    cases = result.scalars().all()
    out = []
    for c in cases:
        # Fetch medical requests for this case
        mr_result = await db.execute(
            select(MedicalRequest).where(MedicalRequest.case_id == c.id)
        )
        med_reqs = mr_result.scalars().all()
        out.append({
            "id": c.id,
            "case_number": c.case_number,
            "customer_id": c.customer_id,
            "current_stage": c.current_stage,
            "kyc_status": c.kyc_status,
            "sum_assured": float(c.sum_assured) if c.sum_assured else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "medical_requests": [
                {
                    "id": mr.id,
                    "requirements": mr.requirements,
                    "status": mr.status,
                    "created_at": mr.created_at.isoformat() if mr.created_at else None,
                }
                for mr in med_reqs
            ],
        })
    return {"cases": out}



class CreateMedicalReqBody(BaseModel):
    case_id: str
    customer_id: str
    requirements: List[str]


class CustomerMedicalReqBody(BaseModel):
    case_id: str
    requirements: List[str]


class ProfileUpdateRequestBody(BaseModel):
    case_id: str
    requested_changes: dict


class ESignRequestBody(BaseModel):
    case_id: str
    consent_text: str | None = None


@router.post("/")
async def create_medical_req(
    body: CreateMedicalReqBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("OPS_ADMIN", "UNDERWRITER", "SUPER_ADMIN")),
):
    req = MedicalRequest(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        customer_id=body.customer_id,
        requirements=body.requirements,
    )
    db.add(req)
    await db.execute(
        update(Case)
        .where(Case.id == body.case_id)
        .values(current_stage=CaseStage.MEDICAL_COORDINATION)
    )
    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "message": "Medical request created"}


@router.post("/customer/request")
async def create_customer_medical_req(
    body: CustomerMedicalReqBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = MedicalRequest(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        customer_id=str(current_user.id),
        requirements=body.requirements,
    )
    db.add(req)
    await db.execute(
        update(Case)
        .where(Case.id == body.case_id)
        .values(current_stage=CaseStage.MEDICAL_COORDINATION)
    )
    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "message": "Customer medical request created"}


@router.get("/customer/requests")
async def list_customer_medical_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(MedicalRequest)
        .where(MedicalRequest.customer_id == str(current_user.id))
        .order_by(MedicalRequest.created_at.desc())
    )
    reqs = r.scalars().all()
    return {
        "requests": [
            {
                "id": q.id,
                "case_id": q.case_id,
                "requirements": q.requirements,
                "status": q.status,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in reqs
        ]
    }


@router.post("/customer/profile-update-request")
async def create_profile_update_request(
    body: ProfileUpdateRequestBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Case).where(
            Case.id == body.case_id, Case.customer_id == str(current_user.id)
        )
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await db.execute(
        update(Case)
        .where(Case.id == body.case_id)
        .values(
            profile_update_request=json.dumps(body.requested_changes),
            kyc_status="PROFILE_UPDATE_REQUESTED",
        )
    )
    await db.commit()
    return {
        "message": "Profile update request submitted",
        "status": "PROFILE_UPDATE_REQUESTED",
    }


@router.post("/customer/esign")
async def mock_esign(
    body: ESignRequestBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ensure case exists and belongs to current user
    result = await db.execute(
        select(Case).where(
            Case.id == body.case_id, Case.customer_id == str(current_user.id)
        )
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Find latest medical request for this case and customer
    mr_result = await db.execute(
        select(MedicalRequest)
        .where(MedicalRequest.case_id == body.case_id, MedicalRequest.customer_id == str(current_user.id))
        .order_by(MedicalRequest.created_at.desc())
    )
    med_req = mr_result.scalars().first()
    if not med_req:
        raise HTTPException(status_code=404, detail="Medical request not found for this case")

    # Mark medical request completed and advance case to UNDERWRITING
    await db.execute(
        update(MedicalRequest)
        .where(MedicalRequest.id == med_req.id)
        .values(status="COMPLETED", reviewed_at=datetime.utcnow())
    )

    await db.execute(
        update(Case)
        .where(Case.id == body.case_id)
        .values(
            esign_status="COMPLETED",
            kyc_status="ACTIVE",
            consent_given=1,
            consent_given_at=datetime.utcnow(),
            current_stage=CaseStage.UNDERWRITING,
        )
    )
    await db.commit()

    # Notify Underwriters & Banker
    from backend.app.services.notification_service import create_in_app_notification
    uw_res = await db.execute(select(User).where(User.role == "UNDERWRITER"))
    for uw in uw_res.scalars().all():
        await create_in_app_notification(
            db,
            recipient_id=uw.id,
            recipient_email=uw.email,
            subject="KYC & Medical Documents Uploaded",
            body=f"Customer has uploaded documents and completed e-Signature for Case {case.case_number}. Ready for underwriting review.",
            reference_id=case.id,
        )
    
    banker_res = await db.execute(select(User).where(User.id == case.banker_id))
    banker = banker_res.scalar_one_or_none()
    if banker:
        await create_in_app_notification(
            db,
            recipient_id=banker.id,
            recipient_email=banker.email,
            subject="Customer Completed eSign",
            body=f"Customer has uploaded KYC & Medical documents and completed e-Signature for Case {case.case_number}.",
            reference_id=case.id,
        )

    logger.info("Customer %s completed eSign for case %s, medical_request %s", current_user.id, body.case_id, med_req.id)
    return {"message": "eSign completed", "status": "COMPLETED", "medical_request_id": med_req.id}


@router.get("/queue")
async def medical_queue(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("OPS_ADMIN", "UNDERWRITER", "SUPER_ADMIN")),
):
    r = await db.execute(
        select(MedicalRequest)
        .where(MedicalRequest.status == "PENDING")
        .order_by(MedicalRequest.created_at)
    )
    reqs = r.scalars().all()
    return {
        "queue": [
            {
                "id": q.id,
                "case_id": q.case_id,
                "requirements": q.requirements,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in reqs
        ]
    }


@router.post("/upload")
async def upload_medical_doc(
    file: UploadFile = File(...),
    medical_request_id: str = Form(...),
    document_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload_dir = os.path.abspath(settings.FILE_UPLOAD_PATH)
    logger.info("Saving uploaded file to dir: %s", upload_dir)
    os.makedirs(upload_dir, exist_ok=True)
    doc_id = str(uuid.uuid4())
    save_name = f"med_{doc_id}_{file.filename}"
    save_path = os.path.join(upload_dir, save_name)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    logger.info("Saved uploaded file: %s (size=%d)", save_path, len(content))
    doc = MedicalDocument(
        id=doc_id,
        medical_request_id=medical_request_id,
        customer_id=str(current_user.id),
        document_type=document_type,
        file_name=file.filename,
        file_path=save_path,
        file_size=len(content),
        mime_type=file.content_type,
    )
    db.add(doc)
    await db.commit()
    return {"message": "Document uploaded", "doc_id": doc_id, "file_path": save_path}


@router.patch("/{req_id}/complete")
async def complete_medical(
    req_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("OPS_ADMIN", "UNDERWRITER", "SUPER_ADMIN")),
):
    r = await db.execute(select(MedicalRequest).where(MedicalRequest.id == req_id))
    req = r.scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Medical request not found")

    await db.execute(
        update(MedicalRequest)
        .where(MedicalRequest.id == req_id)
        .values(
            status="COMPLETED",
            reviewed_by=str(current_user.id),
            reviewed_at=datetime.utcnow(),
        )
    )
    
    await db.execute(
        update(Case)
        .where(Case.id == req.case_id)
        .values(current_stage=CaseStage.UNDERWRITING)
    )
    await db.commit()
    return {"message": "Medical request completed"}
