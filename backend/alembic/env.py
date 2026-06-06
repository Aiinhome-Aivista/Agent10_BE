import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.app.core.database import Base
from backend.app.models.all_models import *  # noqa
from configs.base import settings
config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncmy",""))
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction(): context.run_migrations()

async def run_async_migrations():
    from sqlalchemy.ext.asyncio import async_engine_from_config
    connectable = async_engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online(): asyncio.run(run_async_migrations())
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
