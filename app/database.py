from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# pool_size/max_overflow give headroom over the SQLAlchemy default (5+10) so
# background extraction + normal request traffic don't starve each other.
# pool_pre_ping discards connections the DB dropped while idle (Render's managed
# Postgres closes idle conns), and pool_recycle refreshes them periodically —
# together they prevent "stale connection" errors after quiet periods.
# NOTE: total connections per process ≈ pool_size + max_overflow; if Render runs
# multiple workers, keep (workers × 30) under the Postgres connection limit.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
