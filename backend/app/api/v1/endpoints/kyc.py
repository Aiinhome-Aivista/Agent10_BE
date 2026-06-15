"""
KYC endpoints — upload, status, and banker verification.
"""

import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sql_update
from typing import Optional

from configs.base import settings
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles, decode_token
from backend.app.models.all_models import KycDocument, Case
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/kyc", tags=["kyc"])

UPLOAD_DIR = settings.FILE_UPLOAD_PATH
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_kyc_document(
    case_id: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # save file
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    save_name = f"{uuid.uuid4()}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    async with aiofiles.open(save_path, "wb") as out:
        content = await file.read()
        await out.write(content)

    doc = KycDocument(
        id=str(uuid.uuid4()),
        case_id=case_id,
        customer_id=str(current_user.id),
        document_type=document_type,
        file_name=file.filename or save_name,
        file_path=save_path,
        file_size=len(content),
        mime_type=file.content_type,
        status="PENDING",
    )
    db.add(doc)

    # mark case as pending verification / under review
    r = await db.execute(select(Case).where(Case.id == case_id))
    c = r.scalar_one_or_none()
    if c:
        c.kyc_status = "PENDING"
        db.add(c)

    await db.commit()
    await db.refresh(doc)

    return {"message": "KYC document uploaded", "document": {"id": doc.id, "document_type": doc.document_type, "status": doc.status}}


@router.get("/status/{case_id}")
async def get_kyc_status(case_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(KycDocument).where(KycDocument.case_id == case_id))
    docs = r.scalars().all()
    mapping = {d.document_type: d.status for d in docs}

    # compute overall status
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

    mapping["overall_status"] = overall
    return mapping


@router.get("/documents/{case_id}")
async def get_kyc_documents(case_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(KycDocument).where(KycDocument.case_id == case_id))
    docs = r.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "status": d.status,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in docs
        ]
    }


@router.post("/verify")
async def verify_kyc_document(
    document_id: str = Form(...),
    status: str = Form(...),
    remarks: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BANKER, UserRole.SUPER_ADMIN)),
):
    # validate status
    status = status.upper()
    if status not in {"APPROVED", "REJECTED", "UNDER_REVIEW"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    await db.execute(
        sql_update(KycDocument)
        .where(KycDocument.id == document_id)
        .values(status=status, verified_by=str(current_user.id), verifier_remarks=remarks)
    )

    # refresh case overall status
    r = await db.execute(select(KycDocument).where(KycDocument.id == document_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # compute new overall for case
    r2 = await db.execute(select(KycDocument).where(KycDocument.case_id == doc.case_id))
    docs = r2.scalars().all()
    statuses = {d.status for d in docs}
    if "REJECTED" in statuses:
        overall = "REJECTED"
    elif statuses == {"APPROVED"}:
        overall = "APPROVED"
    elif "UNDER_REVIEW" in statuses or "PENDING" in statuses:
        overall = "UNDER_REVIEW"
    else:
        overall = "PENDING"

    await db.execute(
        sql_update(Case).where(Case.id == doc.case_id).values(kyc_status=overall)
    )
    await db.commit()

    return {"message": "Document verification updated", "overall_status": overall}


@router.get("/{document_id}/view")
async def view_kyc_document(
    document_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ", 1)[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    r = await db.execute(select(KycDocument).where(KycDocument.id == document_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or "application/octet-stream"
    if media_type == "application/octet-stream":
        ext = (os.path.splitext(doc.file_name or "")[1] or "").lower()
        if ext == ".pdf":
            media_type = "application/pdf"
        elif ext == ".txt":
            media_type = "text/plain"
        elif ext in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif ext == ".png":
            media_type = "image/png"
        elif ext == ".gif":
            media_type = "image/gif"
        elif ext == ".bmp":
            media_type = "image/bmp"
        elif ext == ".tiff" or ext == ".tif":
            media_type = "image/tiff"

    return FileResponse(doc.file_path, media_type=media_type, filename=doc.file_name, content_disposition_type="inline")
