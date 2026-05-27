from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from .config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            result = await conn.execute(text("PRAGMA table_info(tasks)"))
            columns = {row[1] for row in result.fetchall()}
            migrations = {
                "conversation_id": "ALTER TABLE tasks ADD COLUMN conversation_id VARCHAR(12)",
                "task_type": "ALTER TABLE tasks ADD COLUMN task_type VARCHAR(20) DEFAULT 'immediate'",
                "schedule": "ALTER TABLE tasks ADD COLUMN schedule VARCHAR(200)",
                "repeat": "ALTER TABLE tasks ADD COLUMN repeat VARCHAR(20) DEFAULT 'none'",
                "save_conversation": "ALTER TABLE tasks ADD COLUMN save_conversation BOOLEAN DEFAULT 1",
                "created_at": "ALTER TABLE tasks ADD COLUMN created_at DATETIME",
                "next_run_at": "ALTER TABLE tasks ADD COLUMN next_run_at DATETIME",
                "last_run_at": "ALTER TABLE tasks ADD COLUMN last_run_at DATETIME",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    await conn.execute(text(statement))


async def get_db():
    async with async_session() as session:
        yield session
