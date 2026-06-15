from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from configs.base import settings

engine = create_async_engine(
    URL.create(
        drivername="mysql+asyncmy",
        username=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        database=settings.MYSQL_DB,
    ),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=10,
    connect_args={"connect_timeout": 8},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        pass  # Alembic handles migrations


async def ensure_compatibility():
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'name'
                """),
            {"schema": settings.MYSQL_DB},
        )
        has_name_column = result.scalar_one()
        if not has_name_column:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN name VARCHAR(200) NOT NULL AFTER id")
            )
        # Ensure must_change_password column exists (added by recent feature)
        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'must_change_password'
                """),
            {"schema": settings.MYSQL_DB},
        )
        has_must_change = result.scalar_one()
        if not has_must_change:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN must_change_password INT DEFAULT 0 AFTER password_hash"
                )
            )
        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND TABLE_NAME = 'cases'
                  AND COLUMN_NAME = 'kyc_status'
                """),
            {"schema": settings.MYSQL_DB},
        )
        if not result.scalar_one():
            await conn.execute(
                text(
                    "ALTER TABLE cases ADD COLUMN kyc_status VARCHAR(50) DEFAULT 'PENDING' AFTER policy_tenure"
                )
            )

        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND TABLE_NAME = 'cases'
                  AND COLUMN_NAME = 'esign_status'
                """),
            {"schema": settings.MYSQL_DB},
        )
        if not result.scalar_one():
            await conn.execute(
                text(
                    "ALTER TABLE cases ADD COLUMN esign_status VARCHAR(50) DEFAULT 'NOT_STARTED' AFTER kyc_status"
                )
            )

        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND TABLE_NAME = 'cases'
                  AND COLUMN_NAME = 'profile_update_request'
                """),
            {"schema": settings.MYSQL_DB},
        )
        if not result.scalar_one():
            await conn.execute(
                text(
                    "ALTER TABLE cases ADD COLUMN profile_update_request TEXT AFTER esign_status"
                )
            )
