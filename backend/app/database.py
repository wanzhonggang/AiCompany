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
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS enterprises ("
                "id VARCHAR(12) PRIMARY KEY, "
                "name VARCHAR(120) NOT NULL, "
                "plan VARCHAR(20) DEFAULT 'trial', "
                "billing_period VARCHAR(20) DEFAULT 'monthly', "
                "payment_status VARCHAR(20) DEFAULT 'trial', "
                "default_provider VARCHAR(50) DEFAULT '', "
                "default_model VARCHAR(150) DEFAULT '', "
                "expires_at DATETIME, "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS user_accounts ("
                "id VARCHAR(12) PRIMARY KEY, "
                "enterprise_id VARCHAR(12) NOT NULL, "
                "username VARCHAR(80) UNIQUE NOT NULL, "
                "password_hash VARCHAR(300) NOT NULL, "
                "role VARCHAR(20) DEFAULT 'admin', "
                "agent_id VARCHAR(12), "
                "display_name VARCHAR(100) DEFAULT '', "
                "enabled BOOLEAN DEFAULT 1, "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS enterprise_llm_keys ("
                "id VARCHAR(12) PRIMARY KEY, "
                "enterprise_id VARCHAR(12) NOT NULL, "
                "provider VARCHAR(50) NOT NULL, "
                "api_key TEXT NOT NULL, "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS operation_logs ("
                "id VARCHAR(12) PRIMARY KEY, "
                "enterprise_id VARCHAR(12) NOT NULL, "
                "actor_user_id VARCHAR(12), "
                "actor_username VARCHAR(80) DEFAULT '', "
                "actor_role VARCHAR(20) DEFAULT '', "
                "actor_agent_id VARCHAR(12), "
                "actor_agent_name VARCHAR(100) DEFAULT '', "
                "action VARCHAR(50) NOT NULL, "
                "target_type VARCHAR(50) NOT NULL, "
                "target_id VARCHAR(12), "
                "target_name VARCHAR(200) DEFAULT '', "
                "detail TEXT DEFAULT '', "
                "created_at DATETIME)"
            ))
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS departments ("
                "id VARCHAR(12) PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, "
                "description TEXT DEFAULT '', "
                "color VARCHAR(7) DEFAULT '#06b6d4', "
                "enterprise_id VARCHAR(12), "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            result = await conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='departments'"
            ))
            department_schema = (result.scalar() or "").upper()
            if "UNIQUE (NAME)" in department_schema or "NAME VARCHAR(100) UNIQUE" in department_schema:
                await conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS departments_migrated ("
                    "id VARCHAR(12) PRIMARY KEY, "
                    "name VARCHAR(100) NOT NULL, "
                    "description TEXT DEFAULT '', "
                    "color VARCHAR(7) DEFAULT '#06b6d4', "
                    "enterprise_id VARCHAR(12), "
                    "created_at DATETIME, "
                    "updated_at DATETIME)"
                ))
                await conn.execute(text(
                    "INSERT OR IGNORE INTO departments_migrated "
                    "(id, name, description, color, enterprise_id, created_at, updated_at) "
                    "SELECT id, name, description, color, enterprise_id, created_at, updated_at FROM departments"
                ))
                await conn.execute(text("DROP TABLE departments"))
                await conn.execute(text("ALTER TABLE departments_migrated RENAME TO departments"))
            for table in ("agents", "departments"):
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                columns = {row[1] for row in result.fetchall()}
                if "enterprise_id" not in columns:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN enterprise_id VARCHAR(12)"))

            table_migrations = {
                "enterprises": {
                    "default_provider": "ALTER TABLE enterprises ADD COLUMN default_provider VARCHAR(50) DEFAULT ''",
                    "default_model": "ALTER TABLE enterprises ADD COLUMN default_model VARCHAR(150) DEFAULT ''",
                },
                "operation_logs": {
                    "actor_agent_id": "ALTER TABLE operation_logs ADD COLUMN actor_agent_id VARCHAR(12)",
                    "actor_agent_name": "ALTER TABLE operation_logs ADD COLUMN actor_agent_name VARCHAR(100) DEFAULT ''",
                },
            }
            for table, migrations in table_migrations.items():
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                columns = {row[1] for row in result.fetchall()}
                for column, statement in migrations.items():
                    if column not in columns:
                        await conn.execute(text(statement))

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
