"""SQLAlchemy 数据模型 —— User、Report、UsageRecord。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return uuid.uuid4().hex[:16]


class User(Base):
    """用户模型。"""

    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(100), default="")
    plan_type = Column(String(20), default="free")  # free / pro / enterprise
    plan_expires_at = Column(DateTime, nullable=True)  # 订阅到期时间
    is_active = Column(Integer, default=1)  # 1=启用 0=禁用
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    reports = relationship("Report", back_populates="user")
    usage_records = relationship("UsageRecord", back_populates="user")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "plan_type": self.plan_type,
            "plan_expires_at": self.plan_expires_at.isoformat() if self.plan_expires_at else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Report(Base):
    """研究报告模型。"""

    __tablename__ = "reports"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    report_type = Column(String(50), nullable=False)  # industry_research/company_deep/macro_brief/strategy_daily
    topic = Column(Text, nullable=False)  # 用户输入的原始研究课题
    content = Column(Text, default="")  # 报告 Markdown 正文
    sources = Column(JSON, default=[])  # 数据来源列表 [{name, url, access_time}]
    status = Column(String(20), default="draft")  # draft / completed / failed
    compliance_status = Column(String(20), default="pending")  # pending / passed / failed
    token_used = Column(Integer, default=0)  # 消耗的 Token 数
    thread_id = Column(String(50), default="")  # 关联的对话线程
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="reports")

    __table_args__ = (
        Index("idx_reports_user_created", "user_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "report_type": self.report_type,
            "topic": self.topic,
            "content": self.content,
            "sources": self.sources,
            "status": self.status,
            "compliance_status": self.compliance_status,
            "token_used": self.token_used,
            "thread_id": self.thread_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UsageRecord(Base):
    """用量记录模型。"""

    __tablename__ = "usage_records"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    record_type = Column(String(30), nullable=False)  # report_generated / token_consumed
    amount = Column(Integer, default=0)  # 用量数值
    metadata_json = Column(JSON, default={})  # 额外元数据
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_user_date", "user_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "record_type": self.record_type,
            "amount": self.amount,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ReportCache(Base):
    """报告缓存 —— 同 query 第二次生成秒级返回。

    缓存 key = md5(user_id + topic + report_type)
    - 命中时不调 LLM，直接返回历史报告
    - 失败任务不缓存
    - 24 小时 TTL
    - 命中次数统计（用于优化热点识别）
    """

    __tablename__ = "report_cache"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    topic_hash = Column(String(64), nullable=False, index=True)  # md5
    topic = Column(Text, nullable=False)  # 原文（回显用）
    report_type = Column(String(50), nullable=False)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    hit_count = Column(Integer, default=0)
    last_hit_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User")
    report = relationship("Report")

    __table_args__ = (
        Index("idx_cache_user_hash", "user_id", "topic_hash"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "topic_hash": self.topic_hash,
            "topic": self.topic,
            "report_type": self.report_type,
            "report_id": self.report_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "hit_count": self.hit_count,
            "last_hit_at": self.last_hit_at.isoformat() if self.last_hit_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Task(Base):
    """后台任务表 —— 异步报告生成。

    状态机：pending → running → completed / failed → (retry) → pending
    """

    __tablename__ = "tasks"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(String(50), default="")
    report_type = Column(String(50), nullable=False)
    topic = Column(Text, nullable=False)
    status = Column(String(20), default="pending", index=True)  # pending / running / completed / failed
    progress = Column(Integer, default=0)  # 0-100
    current_stage = Column(String(50), default="")  # planner/finance_search/finance_knowledge/report_synthesizer
    result_report_id = Column(String(32), ForeignKey("reports.id"), nullable=True)
    error_message = Column(Text, default="")
    celery_task_id = Column(String(64), default="")  # 预留 Celery 迁移
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User")
    report = relationship("Report")

    __table_args__ = (
        Index("idx_tasks_user_status", "user_id", "status"),
        Index("idx_tasks_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "report_type": self.report_type,
            "topic": self.topic,
            "status": self.status,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "result_report_id": self.result_report_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
