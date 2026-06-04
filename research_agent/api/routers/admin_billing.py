"""管理员计费 API 路由 —— 订单管理、退款、统计。"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel

from billing.alipay import get_alipay_client
from db.database import DatabaseManager
from db.repositories.order_repo import OrderRepo
from db.repositories.user_repo import UserRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/billing", tags=["admin-billing"])

# 管理员邮箱白名单（环境变量配置，逗号分隔）
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}


class RefundRequest(BaseModel):
    refund_amount: Optional[float] = None  # None 表示全额退款（单位：元）
    reason: str = "管理员手动退款"


def _require_admin(request: Request) -> str:
    """校验管理员身份：邮箱在 ADMIN_EMAILS 白名单中。返回 user_id。"""
    user_id = getattr(request.state, "user_id", "default_user")
    if user_id == "default_user":
        raise HTTPException(status_code=401, detail="请先登录")
    if not ADMIN_EMAILS:
        logger.warning("ADMIN_EMAILS 未配置，所有用户均无管理员权限")
        raise HTTPException(status_code=403, detail="未配置管理员白名单")

    db_session = DatabaseManager.get_instance().get_session()
    try:
        user = UserRepo(db_session).get_by_id(user_id)
        if not user or user.email.lower() not in ADMIN_EMAILS:
            raise HTTPException(status_code=403, detail="需要管理员权限")
    finally:
        db_session.close()
    return user_id


class OrderAdminItem(BaseModel):
    id: str
    order_no: str
    user_id: str
    plan_type: str
    billing_cycle: str
    amount: int
    amount_yuan: float
    status: str
    payment_method: str
    transaction_id: str
    paid_at: Optional[str] = None
    expired_at: Optional[str] = None
    refund_amount: int
    refund_reason: str
    created_at: str


class StatsResponse(BaseModel):
    total_paid_orders: int
    total_gmv_cents: int
    total_gmv_yuan: float
    today_paid_orders: int
    today_gmv_cents: int
    today_gmv_yuan: float
    refunded_orders: int
    pending_orders: int


@router.get("/orders", response_model=List[OrderAdminItem])
def list_all_orders(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    """管理员：列出全部订单。"""
    _require_admin(request)
    db_session = DatabaseManager.get_instance().get_session()
    try:
        orders = OrderRepo(db_session).list_all(status=status, limit=limit)
        return [OrderAdminItem(**o.to_dict()) for o in orders]
    finally:
        db_session.close()


@router.post("/orders/{order_id}/refund")
def admin_refund(order_id: str, req: RefundRequest, request: Request):
    """管理员：手动退款。"""
    admin_id = _require_admin(request)

    db_session = DatabaseManager.get_instance().get_session()
    try:
        order_repo = OrderRepo(db_session)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.status != "paid":
            raise HTTPException(status_code=400, detail=f"订单状态 {order.status} 不可退款")

        # 默认全额退款
        amount_yuan = req.refund_amount if req.refund_amount is not None else order.amount / 100
        if amount_yuan * 100 > order.amount:
            raise HTTPException(status_code=400, detail="退款金额超过订单金额")
        if amount_yuan <= 0:
            raise HTTPException(status_code=400, detail="退款金额必须大于 0")

        # 调支付宝退款
        alipay = get_alipay_client()
        if alipay.config.is_configured():
            try:
                alipay_result = alipay.refund(
                    order_no=order.order_no,
                    refund_amount=f"{amount_yuan:.2f}",
                    reason=req.reason,
                )
                if alipay_result.get("code") != "10000":
                    raise HTTPException(
                        status_code=502,
                        detail=f"支付宝退款失败: {alipay_result.get('msg', alipay_result)}",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"调支付宝退款失败: {e}")
                raise HTTPException(status_code=502, detail=f"退款失败: {e}")
        else:
            logger.warning(f"支付宝未配置，直接标记退款（开发模式） order={order.order_no}")

        # 标记订单为已退款
        order = order_repo.mark_refunded(order_id, int(amount_yuan * 100), f"[{admin_id}] {req.reason}")
        return {
            "ok": True,
            "order_id": order_id,
            "refund_amount": order.refund_amount,
            "message": "退款成功",
        }
    finally:
        db_session.close()


@router.get("/stats", response_model=StatsResponse)
def admin_stats(request: Request):
    """管理员：支付统计。"""
    _require_admin(request)
    db_session = DatabaseManager.get_instance().get_session()
    try:
        stats = OrderRepo(db_session).stats()
        return StatsResponse(**stats)
    finally:
        db_session.close()
