import json
import sys
import os

# Ensure project root (q2p-api) is on sys.path so imports like `configs` resolve
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from configs.base import settings
from sqlalchemy import create_engine, text

print("Using DB URL (sync):", settings.DATABASE_URL_SYNC)

engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)

with engine.connect() as conn:
    try:
        res = conn.execute(text("""
            SELECT id, name, email, phone, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 50
            """))
        users = [dict(row._mapping) for row in res]
    except Exception as e:
        print("Error querying users:", e)
        users = []

    try:
        res2 = conn.execute(text("""
            SELECT id, banker_id, user_id, source_type, source_filename, normalized_payload, raw_payload, created_at
            FROM customer_intake_records
            ORDER BY created_at DESC
            LIMIT 50
            """))
        intakes = [dict(row._mapping) for row in res2]
    except Exception as e:
        print("Error querying intakes:", e)
        intakes = []

output = {"users": users, "intakes": intakes}
print(json.dumps(output, default=str, indent=2))
