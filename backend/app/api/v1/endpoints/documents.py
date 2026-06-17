"""
Documents endpoint — upload, list, and retrieve case/medical documents.
"""

import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from configs.base import settings
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.user import User, UserRole
from backend.app.models.all_models import MedicalDocument, MedicalRequest
from fastapi import Header
from typing import Optional
from fastapi.responses import FileResponse
from backend.app.core.security import decode_token
from backend.app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = settings.FILE_UPLOAD_PATH
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    medical_request_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a medical or case document."""
    # Validate medical request exists
    result = await db.execute(
        select(MedicalRequest).where(MedicalRequest.id == medical_request_id)
    )
    med_req = result.scalar_one_or_none()
    if not med_req:
        raise HTTPException(status_code=404, detail="Medical request not found")

    # Save file
    ext = os.path.splitext(file.filename)[1] if file.filename else ".bin"
    save_name = f"{uuid.uuid4()}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)

    async with aiofiles.open(save_path, "wb") as out:
        content = await file.read()
        await out.write(content)

    doc = MedicalDocument(
        id=str(uuid.uuid4()),
        medical_request_id=medical_request_id,
        customer_id=med_req.customer_id,
        document_type=document_type,
        file_name=file.filename or save_name,
        file_path=save_path,
        file_size=len(content),
        mime_type=file.content_type,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "message": "Document uploaded",
        "document": {
            "id": doc.id,
            "document_type": doc.document_type,
            "file_name": doc.file_name,
            "file_size": doc.file_size,
            "uploaded_at": doc.uploaded_at.isoformat(),
        },
    }


@router.get("/medical-request/{medical_request_id}")
async def list_documents(
    medical_request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MedicalDocument).where(
            MedicalDocument.medical_request_id == medical_request_id
        )
    )
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "file_size": d.file_size,
                "verified": bool(d.verified),
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in docs
        ]
    }


@router.get("/case/{case_id}")
async def list_documents_by_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents attached to any medical request for a case."""
    # join MedicalDocument -> MedicalRequest to filter by case_id
    from sqlalchemy import join

    j = join(MedicalDocument, MedicalRequest, MedicalDocument.medical_request_id == MedicalRequest.id)
    result = await db.execute(
        select(MedicalDocument).select_from(j).where(MedicalRequest.case_id == case_id)
    )
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "file_size": d.file_size,
                "verified": bool(d.verified),
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in docs
        ]
    }


@router.patch("/{document_id}/verify")
async def verify_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OPS_ADMIN, UserRole.UNDERWRITER, UserRole.SUPER_ADMIN)
    ),
):
    from sqlalchemy import update as sql_update

    await db.execute(
        sql_update(MedicalDocument)
        .where(MedicalDocument.id == document_id)
        .values(verified=1, verified_by=str(current_user.id))
    )
    await db.commit()
    return {"message": "Document verified"}


@router.get("/{document_id}/view")
async def view_medical_document(
    document_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Return the stored medical document file as an inline response.

    Accepts either `token` query parameter or `Authorization: Bearer <token>` header.
    """
    # Resolve token from header if not provided
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    r = await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or "application/octet-stream"
    if not media_type or media_type == "application/octet-stream":
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
