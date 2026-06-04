"""订阅数据仓库。"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from db.models import Subscription

logger = logging.getLogger(__name__)


class SubscriptionRepo:
    """订阅 CRUD 操作。"""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: str,
        plan_type: str,
        billing_cycle: str,
        expires_at: datetime,
        order_no: str = "",
    ) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            plan_type=plan_type,
            billing_cycle=billing_cycle,
            expires_at=expires_at,
            order_no=order_no,
            status="active",
            auto_renew=1,
        )
        self.session.add(sub)
        self.session.commit()
        self.session.refresh(sub)
        return sub

    def get_current(self, user_id: str) -> Optional[Subscription]:
        """获取用户当前活跃订阅。"""
        return (
            self.session.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.expires_at > datetime.now(timezone.utc),
            )
            .order_by(Subscription.expires_at.desc())
            .first()
        )

    def list_by_user(self, user_id: str, limit: int = 50) -> List[Subscription]:
        return (
            self.session.query(Subscription)
            .filter(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
            .all()
        )

    def cancel(self, subscription_id: str) -> Optional[Subscription]:
        """取消订阅（关闭自动续费，到期后不续）。"""
        sub = self.session.query(Subscription).filter(Subscription.id == subscription_id).first()
        if sub and sub.status == "active":
            sub.auto_renew = 0
            sub.status = "cancelled"
            sub.cancelled_at = datetime.now(timezone.utc)
            self.session.commit()
            self.session.refresh(sub)
        return sub

    def expire_overdue(self) -> int:
        """将过期订阅标记为 expired（定时任务调用）。"""
        now = datetime.now(timezone.utc)
        overdue = (
            self.session.query(Subscription)
            .filter(
                Subscription.status == "active",
                Subscription.expires_at <= now,
            )
            .all()
        )
        for sub in overdue:
            sub.status = "expired"
        if overdue:
            self.session.commit()
        return len(overdue)
