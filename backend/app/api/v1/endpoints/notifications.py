"""
Notifications endpoint — list, manage, send, and count notification logs.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import User, UserRole, NotificationLog, Case
from backend.app.repositories.quote_policy_otp_repository import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationBody(BaseModel):
    case_id: str
    customer_id: str
    subject: str
    message: str


# ─── Pending (admin/ops view) ─────────────────────────────────────────
@router.get("/pending")
async def pending_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.SUPER_ADMIN, UserRole.OPS_ADMIN, UserRole.UNDERWRITER)
    ),
):
    repo = NotificationRepository(db)
    items = await repo.list_pending()
    return {"notifications": [_serialize(n) for n in items]}


# ─── My notifications (all roles) ────────────────────────────────────
@router.get("/mine")
async def my_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(NotificationLog)
        .where(NotificationLog.recipient_id == str(current_user.id))
        .order_by(NotificationLog.created_at.desc())
        .limit(50)
    )
    items = result.scalars().all()
    return {"notifications": [_serialize(n) for n in items]}


# ─── Unread count ─────────────────────────────────────────────────────
@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns count of PENDING (unread) notifications for the current user."""
    result = await db.execute(
        select(func.count(NotificationLog.id))
        .where(
            NotificationLog.recipient_id == str(current_user.id),
            NotificationLog.status == "PENDING",
        )
    )
    count = result.scalar() or 0
    return {"count": count}


# ─── Mark read (individual) ───────────────────────────────────────────
@router.post("/{notification_id}/mark-read")
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.id == notification_id,
            NotificationLog.recipient_id == str(current_user.id),
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.status = "SENT"
    notif.sent_at = datetime.utcnow()
    await db.commit()
    return {"message": "Marked as read"}


# ─── Mark all read ────────────────────────────────────────────────────
@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(NotificationLog)
        .where(
            NotificationLog.recipient_id == str(current_user.id),
            NotificationLog.status == "PENDING",
        )
        .values(status="SENT", sent_at=datetime.utcnow())
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


# ─── Send notification (Underwriter → Customer) ───────────────────────
@router.post("/send")
async def send_notification(
    body: SendNotificationBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.UNDERWRITER, UserRole.SUPER_ADMIN, UserRole.OPS_ADMIN, UserRole.BANKER)
    ),
):
    """Underwriter / Banker sends a notification to a specific customer."""
    # Validate customer exists
    result = await db.execute(
        select(User).where(User.id == body.customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")

    notif = NotificationLog(
        id=str(uuid.uuid4()),
        recipient_id=body.customer_id,
        recipient_email=customer.email,
        subject=body.subject,
        body=body.message,
        notification_type="IN_APP",
        reference_type="CASE",
        reference_id=body.case_id,
        status="PENDING",
    )
    db.add(notif)
    await db.commit()
    return {"message": "Notification sent", "id": notif.id}


# ─── Mark sent (admin) ────────────────────────────────────────────────
@router.post("/{notification_id}/mark-sent")
async def mark_sent(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    repo = NotificationRepository(db)
    await repo.mark_sent(notification_id)
    return {"message": "Notification marked as sent"}


def _serialize(n) -> dict:
    return {
        "id": n.id,
        "recipient_email": n.recipient_email,
        "subject": n.subject,
        "body": getattr(n, "body", ""),
        "notification_type": n.notification_type,
        "reference_type": n.reference_type,
        "reference_id": n.reference_id,
        "status": n.status,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
    }
