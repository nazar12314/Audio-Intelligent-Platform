import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from audio_platform.core.config import get_settings
from audio_platform.infrastructure.db import Base, sql_engine

# Import every module that defines ORM models exactly once, so autogenerate sees all tables, e.g.:
# import audio_platform.modules.recordings.adapters.postgres  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().postgres.dsn.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    settings = get_settings()
    async with (
        sql_engine(
            settings.postgres, application_name=f"{settings.service_name}-migrate"
        ) as engine,
        engine.connect() as connection,
    ):
        await connection.run_sync(_run_sync_migrations)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
