"""订单数据仓库。"""

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.models import Order

logger = logging.getLogger(__name__)


def _generate_order_no() -> str:
    """生成商户订单号：年月日时分秒 + 8位随机字符。"""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(4).upper()


class OrderRepo:
    """订单 CRUD 操作。"""

    ORDER_TTL_MINUTES = 15  # 订单默认 15 分钟过期

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: str,
        plan_type: str,
        billing_cycle: str,
        amount: int,
    ) -> Order:
        """创建订单（默认 15 分钟过期）。"""
        now = datetime.now(timezone.utc)
        order = Order(
            order_no=_generate_order_no(),
            user_id=user_id,
            plan_type=plan_type,
            billing_cycle=billing_cycle,
            amount=amount,
            status="pending",
            payment_method="alipay",
            expired_at=now + timedelta(minutes=self.ORDER_TTL_MINUTES),
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_by_id(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def get_by_order_no(self, order_no: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.order_no == order_no).first()

    def list_by_user(self, user_id: str, status: Optional[str] = None, limit: int = 50) -> List[Order]:
        query = self.session.query(Order).filter(Order.user_id == user_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).limit(limit).all()

    def list_all(self, status: Optional[str] = None, limit: int = 100) -> List[Order]:
        """管理员侧：列出全部订单。"""
        query = self.session.query(Order)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).limit(limit).all()

    def mark_paid(self, order_no: str, transaction_id: str) -> Optional[Order]:
        """标记订单已支付（幂等）。"""
        order = self.get_by_order_no(order_no)
        if not order:
            return None
        if order.status == "paid":
            logger.info(f"订单已支付，跳过重复处理: {order_no}")
            return order
        if order.status != "pending":
            logger.warning(f"订单状态非 pending，无法标记为 paid: {order_no} (status={order.status})")
            return order
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)
        order.transaction_id = transaction_id
        self.session.commit()
        self.session.refresh(order)
        return order

    def cancel(self, order_id: str, user_id: str) -> Optional[Order]:
        """用户取消未支付订单。"""
        order = self.get_by_id(order_id)
        if order and order.user_id == user_id and order.status == "pending":
            order.status = "cancelled"
            self.session.commit()
            self.session.refresh(order)
        return order

    def set_qr_code(self, order_id: str, qr_code_url: str) -> Optional[Order]:
        """保存支付宝返回的支付链接。"""
        order = self.get_by_id(order_id)
        if order:
            order.qr_code_url = qr_code_url
            self.session.commit()
            self.session.refresh(order)
        return order

    def mark_refunded(self, order_id: str, refund_amount: int, reason: str) -> Optional[Order]:
        order = self.get_by_id(order_id)
        if not order:
            return None
        if order.status != "paid":
            logger.warning(f"订单状态非 paid，无法退款: {order_id} (status={order.status})")
            return order
        order.status = "refunded"
        order.refund_amount = refund_amount
        order.refund_reason = reason
        order.refunded_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(order)
        return order

    def expire_overdue(self) -> int:
        """将过期未支付订单标记为 cancelled（定时任务调用）。"""
        now = datetime.now(timezone.utc)
        overdue = (
            self.session.query(Order)
            .filter(
                Order.status == "pending",
                Order.expired_at <= now,
            )
            .all()
        )
        for order in overdue:
            order.status = "cancelled"
        if overdue:
            self.session.commit()
        return len(overdue)

    def stats(self) -> dict:
        """管理员：支付统计。"""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        paid_count = self.session.query(func.count(Order.id)).filter(Order.status == "paid").scalar() or 0
        paid_amount = self.session.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.status == "paid").scalar() or 0
        today_count = self.session.query(func.count(Order.id)).filter(Order.status == "paid", Order.paid_at >= today_start).scalar() or 0
        today_amount = self.session.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.status == "paid", Order.paid_at >= today_start).scalar() or 0
        refunded_count = self.session.query(func.count(Order.id)).filter(Order.status == "refunded").scalar() or 0
        pending_count = self.session.query(func.count(Order.id)).filter(Order.status == "pending").scalar() or 0

        return {
            "total_paid_orders": paid_count,
            "total_gmv_cents": int(paid_amount),
            "total_gmv_yuan": round(paid_amount / 100, 2),
            "today_paid_orders": today_count,
            "today_gmv_cents": int(today_amount),
            "today_gmv_yuan": round(today_amount / 100, 2),
            "refunded_orders": refunded_count,
            "pending_orders": pending_count,
        }
