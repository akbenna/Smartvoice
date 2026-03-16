"""
Database connectie — Async SQLAlchemy + asyncpg pool.

Gebruik:
    from shared.database import get_db, engine

    # In FastAPI endpoint:
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))
        users = result.scalars().all()
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config.settings import config

# Async engine met asyncpg
engine = create_async_engine(
    config.db.async_dsn,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    echo=config.is_development,
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency: geeft een database sessie."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Test de database connectie bij startup."""
    async with engine.begin() as conn:
        # Verifieer connectie
        await conn.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )


async def close_db():
    """Sluit de database connectie pool."""
    await engine.dispose()
