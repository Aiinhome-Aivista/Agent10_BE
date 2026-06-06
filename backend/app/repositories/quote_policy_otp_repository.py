"""
Repositories for Quote, Policy, OTP, AuditLog, EscalationLog, NotificationLog
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models.all_models import (
    Quote,
    Policy,
    OTPRecord,
    ConsentRecord,
    EscalationLog,
    NotificationLog,
    AuditLog,
)

# ────────────────────── Quote ──────────────────────


class QuoteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_bulk(self, quotes: List[dict]) -> List[Quote]:
        objs = [Quote(id=str(uuid.uuid4()), **q) for q in quotes]
        self.db.add_all(objs)
        await self.db.commit()
        return objs

    async def list_by_case(self, case_id: str) -> List[Quote]:
        result = await self.db.execute(
            select(Quote).where(Quote.case_id == case_id).order_by(Quote.ai_rank)
        )
        return result.scalars().all()

    async def get_by_id(self, quote_id: str) -> Optional[Quote]:
        result = await self.db.execute(select(Quote).where(Quote.id == quote_id))
        return result.scalar_one_or_none()


# ────────────────────── Policy ──────────────────────


class PolicyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Policy:
        policy = Policy(id=str(uuid.uuid4()), **data)
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)
        return policy

    async def get_by_case(self, case_id: str) -> Optional[Policy]:
        result = await self.db.execute(select(Policy).where(Policy.case_id == case_id))
        return result.scalar_one_or_none()

    async def get_by_customer(self, customer_id: str) -> List[Policy]:
        result = await self.db.execute(
            select(Policy)
            .where(Policy.customer_id == customer_id)
            .order_by(Policy.created_at.desc())
        )
        return result.scalars().all()

    async def list_all(self, skip: int = 0, limit: int = 50) -> List[Policy]:
        result = await self.db.execute(
            select(Policy).order_by(Policy.created_at.desc()).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def update(self, policy_id: str, data: dict) -> Optional[Policy]:
        await self.db.execute(
            update(Policy).where(Policy.id == policy_id).values(**data)
        )
        await self.db.commit()
        result = await self.db.execute(select(Policy).where(Policy.id == policy_id))
        return result.scalar_one_or_none()


# ────────────────────── OTP ──────────────────────


class OTPRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, case_id: str, customer_id: str, otp_hash: str, expiry_minutes: int = 10
    ) -> OTPRecord:
        otp = OTPRecord(
            id=str(uuid.uuid4()),
            case_id=case_id,
            customer_id=customer_id,
            otp_hash=otp_hash,
            expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes),
        )
        self.db.add(otp)
        await self.db.commit()
        await self.db.refresh(otp)
        return otp

    async def get_active(self, case_id: str) -> Optional[OTPRecord]:
        result = await self.db.execute(
            select(OTPRecord)
            .where(
                OTPRecord.case_id == case_id,
                OTPRecord.status == "PENDING",
                OTPRecord.expires_at > datetime.utcnow(),
            )
            .order_by(OTPRecord.created_at.desc())
        )
        return result.scalars().first()

    async def mark_verified(self, otp_id: str):
        await self.db.execute(
            update(OTPRecord)
            .where(OTPRecord.id == otp_id)
            .values(status="VERIFIED", verified_at=datetime.utcnow())
        )
        await self.db.commit()

    async def increment_retry(self, otp_id: str, max_retry: int = 3):
        result = await self.db.execute(select(OTPRecord).where(OTPRecord.id == otp_id))
        otp = result.scalar_one_or_none()
        if otp:
            otp.retry_count += 1
            if otp.retry_count >= max_retry:
                otp.status = "INVALIDATED"
            await self.db.commit()
        return otp


# ────────────────────── Consent ──────────────────────


class ConsentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> ConsentRecord:
        record = ConsentRecord(id=str(uuid.uuid4()), **data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def list_by_case(self, case_id: str) -> List[ConsentRecord]:
        result = await self.db.execute(
            select(ConsentRecord).where(ConsentRecord.case_id == case_id)
        )
        return result.scalars().all()

    async def list_all(self, skip: int = 0, limit: int = 50) -> List[ConsentRecord]:
        result = await self.db.execute(
            select(ConsentRecord)
            .order_by(ConsentRecord.consented_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()


# ────────────────────── Audit ──────────────────────


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> AuditLog:
        log = AuditLog(id=str(uuid.uuid4()), **data)
        self.db.add(log)
        await self.db.commit()
        return log

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_case(self, case_id: str) -> List[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.created_at.desc())
        )
        return result.scalars().all()


# ────────────────────── Escalation ──────────────────────


class EscalationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> EscalationLog:
        log = EscalationLog(id=str(uuid.uuid4()), **data)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def list_unresolved(self) -> List[EscalationLog]:
        result = await self.db.execute(
            select(EscalationLog)
            .where(EscalationLog.resolved == 0)
            .order_by(EscalationLog.created_at.desc())
        )
        return result.scalars().all()

    async def list_all(self, skip: int = 0, limit: int = 50) -> List[EscalationLog]:
        result = await self.db.execute(
            select(EscalationLog)
            .order_by(EscalationLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def resolve(self, escalation_id: str):
        await self.db.execute(
            update(EscalationLog)
            .where(EscalationLog.id == escalation_id)
            .values(resolved=1, resolved_at=datetime.utcnow())
        )
        await self.db.commit()


# ────────────────────── Notification ──────────────────────


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> NotificationLog:
        log = NotificationLog(id=str(uuid.uuid4()), **data)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def mark_sent(self, notification_id: str):
        await self.db.execute(
            update(NotificationLog)
            .where(NotificationLog.id == notification_id)
            .values(status="SENT", sent_at=datetime.utcnow())
        )
        await self.db.commit()

    async def list_pending(self) -> List[NotificationLog]:
        result = await self.db.execute(
            select(NotificationLog).where(NotificationLog.status == "PENDING").limit(50)
        )
        return result.scalars().all()
