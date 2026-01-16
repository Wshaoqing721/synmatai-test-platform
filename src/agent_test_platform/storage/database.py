
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect, text
from agent_test_platform.config.settings import settings
from agent_test_platform.config.logger import logger
from agent_test_platform.models.base import Base


def _load_all_models() -> None:
    """Import all model modules so they are registered with SQLAlchemy metadata."""

    import importlib

    module_names = [
        "agent_test_platform.models.test_run",
        "agent_test_platform.models.virtual_user",
        "agent_test_platform.models.test_step",
        "agent_test_platform.models.test_result",
        "agent_test_platform.models.node_based",
    ]

    for module_name in module_names:
        importlib.import_module(module_name)


class Database:
    """数据库操作接口"""
    
    def __init__(self):
        self.engine = None
        self.async_session = None
        self.db_path = Path(settings.DATABASE_PATH)
    
    async def initialize(self):
        """初始化数据库"""
        
        try:
            database_url = settings.DATABASE_URL

            # SQLite 兼容：如果仍使用 sqlite:// 或 sqlite+aiosqlite://，则将数据库文件放到 DATABASE_PATH 目录下
            if database_url.startswith("sqlite://") or database_url.startswith("sqlite+aiosqlite://"):
                # 确保数据目录存在（DATABASE_PATH 约定为目录）
                self.db_path.mkdir(parents=True, exist_ok=True)

                # 将 sqlite 文件固定为 results 目录下的 test_platform.db
                db_file = (self.db_path / "test_platform.db").resolve()
                database_url = f"sqlite+aiosqlite:///{db_file}"
                logger.info(f"Using SQLite database: {db_file}")
            else:
                logger.info("Using SQL database via DATABASE_URL")

            self.engine = create_async_engine(
                database_url,
                echo=settings.DEBUG,
            )
            
            # 确保所有模型已被加载到 Base.metadata（否则 create_all 不会创建新表）
            _load_all_models()

            # 创建表
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                # 兼容旧 schema：确保 scenarios.status 存在
                def _ensure_schema(sync_conn):
                    inspector = inspect(sync_conn)
                    if "scenarios" not in inspector.get_table_names():
                        return

                    cols = {c["name"] for c in inspector.get_columns("scenarios")}
                    if "status" in cols:
                        return

                    dialect = sync_conn.dialect.name
                    if dialect == "postgresql":
                        sync_conn.execute(
                            text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS status VARCHAR(20)")
                        )
                    else:
                        # SQLite/MySQL 等不一定支持 IF NOT EXISTS（SQLite 不支持），先检查再加
                        sync_conn.execute(text("ALTER TABLE scenarios ADD COLUMN status VARCHAR(20)"))

                    logger.info("Added missing column: scenarios.status")

                await conn.run_sync(_ensure_schema)
            
            # 会话工厂
            self.async_session = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            logger.info("Database initialized")
        
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def create(self, model):
        """创建记录"""
        async with self.async_session() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model
    
    async def update(self, model):
        """更新记录"""
        async with self.async_session() as session:
            merged = await session.merge(model)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def delete(self, model) -> None:
        """删除记录"""
        async with self.async_session() as session:
            await session.delete(model)
            await session.commit()
    
    async def get(self, model_class, model_id: str, options=None):
        """获取记录

        Args:
            model_class: SQLAlchemy ORM model
            model_id: primary key value
            options: optional SQLAlchemy loader options (e.g. selectinload)
        """
        async with self.async_session() as session:
            if not options:
                return await session.get(model_class, model_id)

            from sqlalchemy import select

            stmt = select(model_class).options(*options).where(model_class.id == model_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    async def query_all(self, model_class, options=None):
        """查询所有记录"""
        from sqlalchemy import select

        async with self.async_session() as session:
            stmt = select(model_class)
            if options:
                stmt = stmt.options(*options)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def query_by_field(self, model_class, field_name, value, options=None):
        """按字段查询"""
        from sqlalchemy import select

        async with self.async_session() as session:
            stmt = select(model_class).where(getattr(model_class, field_name) == value)
            if options:
                stmt = stmt.options(*options)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def query_steps(self, user_id: str):
        """查询用户的所有步骤"""
        from sqlalchemy import select
        from agent_test_platform.models.test_step import TestStep
        
        async with self.async_session() as session:
            stmt = select(TestStep).where(TestStep.virtual_user_id == user_id)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def close(self):
        """关闭数据库连接"""
        if self.engine:
            await self.engine.dispose()

