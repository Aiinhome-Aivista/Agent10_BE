import asyncio
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
# Also add the backend folder
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from sqlalchemy import select
from backend.app.core.database import get_db, engine, Base
from backend.app.models.all_models import KnowledgeDocument

async def main():
    async with engine.begin() as conn:
        # We just want to check if connection is working and list documents
        pass
    
    from sqlalchemy.ext.asyncio import AsyncSession
    async_session = AsyncSession(engine)
    async with async_session as session:
        r = await session.execute(select(KnowledgeDocument))
        docs = r.scalars().all()
        print(f"Total documents: {len(docs)}")
        for d in docs:
            print(f"- ID: {d.id}, Title: {d.title}, Status: {d.status}, Chunks: {d.chunk_count}")

if __name__ == "__main__":
    asyncio.run(main())
