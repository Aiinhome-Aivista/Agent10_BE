import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..models.case import Case, CaseStage, CaseStatus


class CaseRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Case:
        case = Case(
            id=str(uuid.uuid4()),
            case_number=f"CASE-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
            **data,
        )
        self.db.add(case)
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def get_by_id(self, case_id: str) -> Optional[Case]:
        result = await self.db.execute(select(Case).where(Case.id == case_id))
        return result.scalar_one_or_none()

    async def get_by_case_number(self, case_number: str) -> Optional[Case]:
        result = await self.db.execute(select(Case).where(Case.case_number == case_number))
        return result.scalar_one_or_none()

    async def list_by_banker(self, banker_id: str) -> List[Case]:
        result = await self.db.execute(
            select(Case).where(Case.banker_id == banker_id).order_by(Case.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_customer(self, customer_id: str) -> List[Case]:
        result = await self.db.execute(
            select(Case).where(Case.customer_id == customer_id).order_by(Case.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_stage(self, stage: CaseStage) -> List[Case]:
        result = await self.db.execute(
            select(Case).where(Case.current_stage == stage).order_by(Case.created_at.desc())
        )
        return result.scalars().all()

    async def list_all(self, skip: int = 0, limit: int = 50) -> List[Case]:
        result = await self.db.execute(
            select(Case).order_by(Case.created_at.desc()).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def update_stage(self, case_id: str, stage: CaseStage) -> Optional[Case]:
        await self.db.execute(
            update(Case)
            .where(Case.id == case_id)
            .values(current_stage=stage, stage_entered_at=datetime.utcnow(), last_activity_at=datetime.utcnow())
        )
        await self.db.commit()
        return await self.get_by_id(case_id)

    async def update(self, case_id: str, data: dict) -> Optional[Case]:
        await self.db.execute(
            update(Case).where(Case.id == case_id).values(**data, last_activity_at=datetime.utcnow())
        )
        await self.db.commit()
        return await self.get_by_id(case_id)

    async def get_stale_cases(self, minutes: int) -> List[Case]:
        from sqlalchemy import func
        threshold = datetime.utcnow().__class__.utcnow() if False else datetime.utcnow()
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.db.execute(
            select(Case).where(
                Case.status.in_([CaseStatus.ACTIVE, CaseStatus.PENDING]),
                Case.current_stage != CaseStage.COMPLETED,
                Case.stage_entered_at < cutoff,
            )
        )
        return result.scalars().all()
