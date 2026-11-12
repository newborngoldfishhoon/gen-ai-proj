"""Async SQLAlchemy engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    """Return a cached async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if "asyncpg" in settings.database_url:
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0

        pool_options: dict[str, int] = {}
        if not settings.database_url.startswith("sqlite"):
            pool_options.update(pool_size=5, max_overflow=10)

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.environment == "development",
            pool_pre_ping=True,
            connect_args=connect_args,
            **pool_options,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a cached session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine():
    """Dispose the engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
