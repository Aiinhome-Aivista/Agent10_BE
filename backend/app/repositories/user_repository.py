from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.models.all_models import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str):
        normalized = (email or "").strip().lower()
        r = await self.db.execute(select(User).where(User.email == normalized))
        return r.scalar_one_or_none()

    async def get_by_phone(self, phone: str):
        normalized = (phone or "").strip()
        r = await self.db.execute(select(User).where(User.phone == normalized))
        return r.scalar_one_or_none()

    async def get_by_id(self, user_id: str):
        r = await self.db.execute(select(User).where(User.id == user_id))
        return r.scalar_one_or_none()

    async def create_user(self, data: dict) -> User:
        user = User(**data)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
