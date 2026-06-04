"""SQLAlchemy 数据模型 —— User、Report、UsageRecord。"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utc_iso(dt) -> str:
    """统一把 datetime 序列化为带 Z 后缀的 UTC ISO 字符串（避免 JS 解析时区错乱）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # 朴素 datetime 视为 UTC
        dt = dt.replace(tzinfo=timezone.utc)
    # 用 isoformat() 然后把 +00:00 替换为 Z
    return dt.isoformat().replace("+00:00", "Z")


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
            "plan_expires_at": _utc_iso(self.plan_expires_at) if self.plan_expires_at else None,
            "is_active": self.is_active,
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
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
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
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
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
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
            "expires_at": _utc_iso(self.expires_at) if self.expires_at else None,
            "hit_count": self.hit_count,
            "last_hit_at": _utc_iso(self.last_hit_at) if self.last_hit_at else None,
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
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
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
            "updated_at": _utc_iso(self.updated_at) if self.updated_at else None,
            "started_at": _utc_iso(self.started_at) if self.started_at else None,
            "completed_at": _utc_iso(self.completed_at) if self.completed_at else None,
        }


class Subscription(Base):
    """订阅记录表。

    状态机：active → cancelled / expired
    一条记录代表一个完整订阅周期，到期后创建新记录。
    """

    __tablename__ = "subscriptions"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    plan_type = Column(String(20), nullable=False)  # pro / enterprise
    billing_cycle = Column(String(20), nullable=False)  # monthly / yearly
    status = Column(String(20), default="active", index=True)  # active / cancelled / expired
    started_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)
    auto_renew = Column(Integer, default=1)  # 1=开启 0=关闭
    cancelled_at = Column(DateTime, nullable=True)
    order_no = Column(String(64), default="")  # 关联的首单订单号
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = relationship("User")

    __table_args__ = (
        Index("idx_subs_user_status", "user_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plan_type": self.plan_type,
            "billing_cycle": self.billing_cycle,
            "status": self.status,
            "started_at": _utc_iso(self.started_at) if self.started_at else None,
            "expires_at": _utc_iso(self.expires_at) if self.expires_at else None,
            "auto_renew": bool(self.auto_renew),
            "cancelled_at": _utc_iso(self.cancelled_at) if self.cancelled_at else None,
            "order_no": self.order_no,
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
        }


class Order(Base):
    """订单表。

    状态机：pending → paid / failed / cancelled → refunded
    """

    __tablename__ = "orders"

    id = Column(String(32), primary_key=True, default=_new_uuid)
    order_no = Column(String(64), unique=True, nullable=False, index=True)  # 商户订单号
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    plan_type = Column(String(20), nullable=False)
    billing_cycle = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)  # 单位：分
    status = Column(String(20), default="pending", index=True)  # pending / paid / failed / cancelled / refunded
    payment_method = Column(String(20), default="alipay")
    qr_code_url = Column(Text, default="")  # 支付宝返回的支付链接（用于生成二维码）
    paid_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=False)  # 订单过期时间（默认 15 分钟）
    transaction_id = Column(String(64), default="")  # 支付宝交易号
    refund_amount = Column(Integer, default=0)  # 退款金额（分）
    refund_reason = Column(Text, default="")
    refunded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = relationship("User")

    __table_args__ = (
        Index("idx_orders_user_created", "user_id", "created_at"),
        Index("idx_orders_status", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "order_no": self.order_no,
            "user_id": self.user_id,
            "plan_type": self.plan_type,
            "billing_cycle": self.billing_cycle,
            "amount": self.amount,
            "amount_yuan": self.amount / 100,  # 便于前端展示
            "status": self.status,
            "payment_method": self.payment_method,
            "qr_code_url": self.qr_code_url,
            "paid_at": _utc_iso(self.paid_at) if self.paid_at else None,
            "expired_at": _utc_iso(self.expired_at) if self.expired_at else None,
            "transaction_id": self.transaction_id,
            "refund_amount": self.refund_amount,
            "refund_reason": self.refund_reason,
            "refunded_at": _utc_iso(self.refunded_at) if self.refunded_at else None,
            "created_at": _utc_iso(self.created_at) if self.created_at else None,
        }
