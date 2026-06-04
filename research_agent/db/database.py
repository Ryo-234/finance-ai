"""数据库连接管理 —— 同时支持 SQLite（开发）和 PostgreSQL（生产）。"""

import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器（单例）—— 自动适配 SQLite 或 PostgreSQL。

    - 通过 DATABASE_URL 环境变量切换：
      - 未设置 → SQLite（开发，默认）
      - 设置为 postgresql://... → PostgreSQL（生产）
    - 适配不同的连接池和初始化参数
    """

    _instance = None

    def __init__(self):
        database_url = os.environ.get("DATABASE_URL", "").strip()

        if database_url.startswith("postgresql") or database_url.startswith("postgres"):
            # ============== PostgreSQL（生产）==============
            # Render 提供的 URL 可能是 postgres://，SQLAlchemy 2.0 需要 postgresql://
            db_url = database_url.replace("postgres://", "postgresql://", 1)
            self.engine = create_engine(
                db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # 自动重连断开的连接
                pool_recycle=1800,   # 30 分钟回收连接（防 PostgreSQL idle timeout）
                echo=False,
            )
            logger.info(f"数据库已连接（PostgreSQL）")
        else:
            # ============== SQLite（开发/默认）==============
            db_path = Path(os.environ.get("DB_PATH", "./data/finance_agent.db"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path.absolute()}"

            self.engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False, "timeout": 30},
                pool_size=10,
                max_overflow=5,
                pool_pre_ping=True,
                echo=False,
            )

            # 启用 WAL 模式提升 SQLite 并发性能
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            logger.info(f"数据库已连接（SQLite）: {db_path}")

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_tables(self):
        """创建所有表（如果不存在）。"""
        from .models import Base, User

        Base.metadata.create_all(bind=self.engine)
        logger.info("数据库表已就绪")

        # 初始化占位用户（仅 SQLite 模式）
        if not os.environ.get("DATABASE_URL"):
            with self.get_session() as session:
                default_user = session.query(User).filter(User.id == "default_user").first()
                if not default_user:
                    default_user = User(
                        id="default_user",
                        email="guest@finance-ai.local",
                        hashed_password="!guest-no-login!",
                        display_name="访客",
                        plan_type="free",
                    )
                    session.add(default_user)
                    session.commit()
                    logger.info("已创建默认访客用户")

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
