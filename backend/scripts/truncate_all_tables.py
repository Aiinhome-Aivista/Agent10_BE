"""Truncate all tables in the configured MySQL database.

Usage:
    python -m backend.scripts.truncate_all_tables --yes

This script is intentionally destructive. Pass --yes to confirm.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from backend.app.core.database import engine


async def truncate_all_tables() -> list[str]:
    async with engine.begin() as conn:
        result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """))
        table_names = [row[0] for row in result.fetchall()]

        if not table_names:
            return []

        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table_name in table_names:
                await conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))
        finally:
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    return table_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Truncate all tables in the database")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that you want to delete all rows from all tables.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if not args.yes:
        response = input(
            "This will truncate all tables in the current database. Type YES to continue: "
        ).strip()
        if response != "YES":
            raise SystemExit("Aborted")

    table_names = await truncate_all_tables()
    if table_names:
        print(f"Truncated {len(table_names)} tables:")
        for table_name in table_names:
            print(f"- {table_name}")
    else:
        print("No tables found to truncate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
