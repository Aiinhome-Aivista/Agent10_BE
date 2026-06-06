"""Helpers for creating notification records and sending email automatically."""

from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.all_models import NotificationLog
from backend.app.repositories.quote_policy_otp_repository import NotificationRepository
from smtp.smtp_service import smtp_service


async def _deliver_notification(notification_id: str) -> None:
    async with AsyncSessionLocal() as session:
        repo = NotificationRepository(session)
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if not notification:
            return

        try:
            sent = await smtp_service.send(
                notification.recipient_email, notification.subject, notification.body
            )
            if sent:
                await repo.mark_sent(notification_id)
            else:
                await session.execute(
                    NotificationLog.__table__.update()
                    .where(NotificationLog.id == notification_id)
                    .values(
                        status="PENDING",
                        error_message="SMTP delivery failed",
                    )
                )
                await session.commit()
        except Exception as exc:
            await session.execute(
                NotificationLog.__table__.update()
                .where(NotificationLog.id == notification_id)
                .values(
                    status="PENDING",
                    error_message=str(exc),
                )
            )
            await session.commit()


async def queue_and_send_email(
    db: AsyncSession,
    recipient_email: str,
    subject: str,
    body: str,
    *,
    recipient_id: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    notification_type: str = "EMAIL",
) -> NotificationLog:
    repo = NotificationRepository(db)
    log = await repo.create(
        {
            "recipient_id": recipient_id,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "notification_type": notification_type,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "status": "PENDING",
        }
    )

    asyncio.create_task(_deliver_notification(log.id))
    return log


async def queue_and_send_email_batch(
    db: AsyncSession,
    items: list[dict],
) -> list[NotificationLog]:
    import uuid
    logs = []
    for item in items:
        if "status" not in item:
            item["status"] = "PENDING"
        if "notification_type" not in item:
            item["notification_type"] = "EMAIL"
        log = NotificationLog(id=str(uuid.uuid4()), **item)
        db.add(log)
        logs.append(log)
    await db.commit()
    for log in logs:
        asyncio.create_task(_deliver_notification(log.id))
    return logs


def stage_message(case_number: str, stage: str, summary: str) -> tuple[str, str]:
    subject = f"Q2P Update - {case_number} moved to {stage}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;
                background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="margin:0 0 12px;color:#111827;">Case Update</h2>
        <p style="margin:0 0 8px;color:#374151;">Case <strong>{case_number}</strong> moved to <strong>{stage}</strong>.</p>
        <p style="margin:0;color:#6b7280;">{summary}</p>
    </div>
    """
    return subject, body


def customer_invite_message(
    name: str, email: str, user_id: str, temp_password: str
) -> tuple[str, str]:
    subject = "Your Q2P customer profile is ready"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;
                background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="margin:0 0 12px;color:#111827;">Welcome to Q2P</h2>
        <p style="margin:0 0 8px;color:#374151;">Hello {name}, your profile has been created for <strong>{email}</strong>.</p>
        <p style="margin:0 0 8px;color:#374151;">Username / Email: <strong>{email}</strong></p>
        <p style="margin:0 0 8px;color:#374151;">Temporary Password: <strong>{temp_password}</strong></p>
        <p style="margin:0 0 8px;color:#374151;">For your security you must change your password on first login.</p>
        <p style="margin:0;color:#6b7280;">Sign in at <a href="{"/"}">Q2P</a> and complete the onboarding flow. If you have any issues contact your banker.</p>
    </div>
    """
    return subject, body
