"""Customer query endpoints: list pending queries and reply/upload responses"""
from datetime import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Case, CaseStage, EscalationLog, MedicalRequest, MedicalDocument, User

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("/mine")
async def my_queries(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    # Return escalations assigned to the current customer's cases and not resolved, with their medical requests
    r = await db.execute(
        select(EscalationLog)
        .join(Case, Case.id == EscalationLog.case_id)
        .where(
            EscalationLog.assigned_to_role == "CUSTOMER",
            EscalationLog.resolved == 0,
            Case.customer_id == str(current_user.id)
        )
    )
    items = r.scalars().all()
    results = []
    for e in items:
        # load case summary
        cr = await db.execute(select(Case).where(Case.id == e.case_id))
        c = cr.scalar_one_or_none()
        
        # fetch associated MedicalRequest for this query
        mr_res = await db.execute(
            select(MedicalRequest)
            .where(MedicalRequest.case_id == e.case_id, MedicalRequest.status == "PENDING")
            .order_by(MedicalRequest.created_at.desc())
        )
        med_req = mr_res.scalars().first()
        
        results.append({
            "id": e.id,
            "case_id": e.case_id,
            "case_number": c.case_number if c else None,
            "reason": e.reason,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "resolved": e.resolved,
            "requirements": med_req.requirements if med_req else [],
            "medical_request_id": med_req.id if med_req else None,
        })
    return {"queries": results}


@router.post("/{escalation_id}/reply")
async def reply_query(escalation_id: str, message: str | None = Form(None), files: List[UploadFile] = File(None), db: AsyncSession = Depends(get_db), current_user=Depends(require_roles("CUSTOMER","SUPER_ADMIN"))):
    # Create or reuse pending medical request, mark escalation resolved, and move case back to UNDERWRITING
    r = await db.execute(select(EscalationLog).where(EscalationLog.id == escalation_id))
    e = r.scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Escalation not found")
    # ensure case exists
    cr = await db.execute(select(Case).where(Case.id == e.case_id))
    case = cr.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    if str(case.customer_id) != str(current_user.id):
        raise HTTPException(403, "Not authorized to reply to this query")

    # create or reuse a pending MedicalRequest for uploads
    mr_res = await db.execute(
        select(MedicalRequest)
        .where(
            MedicalRequest.case_id == e.case_id,
            MedicalRequest.customer_id == str(current_user.id),
            MedicalRequest.status == "PENDING",
        )
        .order_by(MedicalRequest.created_at.desc())
    )
    med_req = mr_res.scalars().first()
    if not med_req:
        med_req = MedicalRequest(
            id=str(uuid.uuid4()),
            case_id=e.case_id,
            customer_id=str(current_user.id),
            requirements=[e.reason or "QUERY_RESPONSE"],
            status="PENDING",
            ops_remarks="Customer response to query",
        )
        db.add(med_req)
        await db.commit()
        await db.refresh(med_req)

    # Save uploaded files if any
    if files:
        import os
        import aiofiles
        from configs.base import settings
        
        upload_dir = settings.FILE_UPLOAD_PATH
        os.makedirs(upload_dir, exist_ok=True)
        
        for file in files:
            if not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1] or ".bin"
            save_name = f"med_{uuid.uuid4()}{ext}"
            save_path = os.path.join(upload_dir, save_name)
            
            content = await file.read()
            async with aiofiles.open(save_path, "wb") as out:
                await out.write(content)
                
            doc_type = (med_req.requirements[0] if med_req.requirements else None) or e.reason or "QUERY_RESPONSE"
            doc = MedicalDocument(
                id=str(uuid.uuid4()),
                medical_request_id=med_req.id,
                customer_id=str(current_user.id),
                document_type=doc_type,
                file_name=file.filename,
                file_path=save_path,
                file_size=len(content),
                mime_type=file.content_type,
            )
            db.add(doc)
            
        med_req.status = "COMPLETED"
        db.add(med_req)

    e.resolved = 1
    e.resolved_at = datetime.utcnow()
    e.resolved_by = str(current_user.id)
    db.add(e)
    await db.execute(
        update(Case)
        .where(Case.id == case.id)
        .values(current_stage=CaseStage.UNDERWRITING)
    )
    await db.commit()
    return {"message": "Reply recorded, underwriter notified", "medical_request_id": med_req.id}
