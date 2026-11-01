"""Async SQLAlchemy engine lifecycle for PostgreSQL."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from audio_platform.core.config import PostgresSettings


@asynccontextmanager
async def sql_engine(
    settings: PostgresSettings, *, application_name: str
) -> AsyncIterator[AsyncEngine]:
    """
    Create the process-wide engine and dispose of its pool on exit. Connects lazily.
    """
    engine = create_async_engine(
        settings.dsn.get_secret_value(),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_s,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.connect_timeout_s,
            "server_settings": {
                "application_name": application_name,
                "statement_timeout": str(settings.statement_timeout_ms),
            },
        },
    )
    try:
        yield engine
    finally:
        await engine.dispose()


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
