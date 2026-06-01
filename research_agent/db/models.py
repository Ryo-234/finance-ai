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
