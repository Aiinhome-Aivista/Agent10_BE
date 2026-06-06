import asyncio
import json
import os
import sys

proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from configs.base import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    print("Using DB URL:", settings.DATABASE_URL)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async with engine.connect() as conn:
        users_res = await conn.execute(text("""
                SELECT id, name, email, phone, role, must_change_password, created_at
                FROM users
                ORDER BY created_at DESC
                LIMIT 20
                """))
        intakes_res = await conn.execute(text("""
                SELECT id, banker_id, user_id, source_type, source_filename, JSON_EXTRACT(normalized_payload, '$.name') AS name, JSON_EXTRACT(normalized_payload, '$.email') AS email, created_at
                FROM customer_intake_records
                ORDER BY created_at DESC
                LIMIT 20
                """))
        print(
            json.dumps(
                {
                    "users": [dict(r._mapping) for r in users_res],
                    "intakes": [dict(r._mapping) for r in intakes_res],
                },
                default=str,
                indent=2,
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
