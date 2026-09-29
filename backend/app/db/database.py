"""
backend/app/db/database.py
SQLite database setup via SQLAlchemy async.
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./digital_twin.db")

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        from backend.app.db.models import WellRecord, CycleRecord, AlertRecord  # noqa
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency: yield an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
