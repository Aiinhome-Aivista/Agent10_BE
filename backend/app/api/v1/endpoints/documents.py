"""
Documents endpoint — upload, list, and retrieve case/medical documents.
"""

import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.user import User, UserRole
from backend.app.models.all_models import MedicalDocument, MedicalRequest

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = os.getenv("FILE_UPLOAD_PATH", "/tmp/q2p-uploads")
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
        customer_id=str(current_user.id),
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
