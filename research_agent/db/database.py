"""SQLite 数据库连接管理（MVP 阶段）。"""

import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# 数据库文件路径
DB_PATH = Path(os.environ.get("DB_PATH", "./data/finance_agent.db"))


class DatabaseManager:
    """SQLite 数据库管理器（单例）。"""

    _instance = None

    def __init__(self):
        db_dir = DB_PATH.parent
        db_dir.mkdir(parents=True, exist_ok=True)

        db_url = f"sqlite:///{DB_PATH.absolute()}"
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        # 启用 WAL 模式提升并发性能
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        logger.info(f"数据库已连接: {DB_PATH}")

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_tables(self):
        """创建所有表（如果不存在）。"""
        from .models import Base

        Base.metadata.create_all(bind=self.engine)
        logger.info("数据库表已就绪")

    def get_session(self) -> Session:
        """获取一个新的数据库会话。"""
        return self.SessionLocal()


def init_db():
    """初始化数据库（创建表和索引）。"""
    manager = DatabaseManager.get_instance()
    manager.create_tables()
    return manager


def get_db() -> Session:
    """获取数据库会话（用于依赖注入）。"""
    manager = DatabaseManager.get_instance()
    session = manager.get_session()
    try:
        yield session
    finally:
        session.close()
