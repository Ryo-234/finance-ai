"""计费 API 路由 —— 方案查询、用量统计、订单、订阅、支付回调。"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from billing.plans import SUBSCRIPTION_PLANS, get_plan_limits
from billing.quota_manager import QuotaManager
from billing.subscription import SubscriptionService
from billing.alipay import get_alipay_client, generate_qr_code
from db.database import DatabaseManager
from db.repositories.order_repo import OrderRepo
from db.repositories.subscription_repo import SubscriptionRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ============== 响应模型 ==============

class PlanInfo(BaseModel):
    plan_type: str
    name: str
    monthly_price: int
    monthly_reports: int
    max_tokens_per_month: int
    features: List[str]


class UsageInfo(BaseModel):
    reports_this_month: int
    tokens_this_month: int
    report_limit: int
    token_limit: int
    daily_stats: list


class CreateOrderRequest(BaseModel):
    plan_type: str = Field(..., description="pro / enterprise")
    billing_cycle: str = Field("monthly", description="monthly / yearly")


class OrderResponse(BaseModel):
    id: str
    order_no: str
    plan_type: str
    billing_cycle: str
    amount: int
    amount_yuan: float
    status: str
    payment_method: str
    qr_code_url: str
    expired_at: str
    paid_at: Optional[str] = None
    created_at: str


class SubscriptionResponse(BaseModel):
    plan_type: str
    billing_cycle: str
    status: str
    expires_at: str
    auto_renew: bool
    started_at: str


# ============== 方案与用量 ==============

@router.get("/plans", response_model=List[PlanInfo])
def list_plans():
    """获取所有订阅方案。"""
    return [
        PlanInfo(
            plan_type=key,
            name=plan["name"],
            monthly_price=plan["monthly_price"],
            monthly_reports=plan["monthly_reports"],
            max_tokens_per_month=plan["max_tokens_per_month"],
            features=plan.get("features", []),
        )
        for key, plan in SUBSCRIPTION_PLANS.items()
    ]


@router.get("/usage", response_model=UsageInfo)
def get_usage(request: Request):
    """获取当前用户的用量统计。"""
    user_id = getattr(request.state, "user_id", "default_user")
    plan_type = getattr(request.state, "plan_type", "free")

    limits = get_plan_limits(plan_type)
    db_session = DatabaseManager.get_instance().get_session()
    try:
        quota = QuotaManager(db_session)
        current = quota.get_current_usage(user_id)
    finally:
        db_session.close()

    return UsageInfo(
        reports_this_month=current["reports_this_month"],
        tokens_this_month=current["tokens_this_month"],
        report_limit=limits["monthly_reports"],
        token_limit=limits["max_tokens_per_month"],
        daily_stats=current["daily_stats"],
    )


# ============== 订单 ==============

def _compute_order_amount(plan_type: str, billing_cycle: str) -> int:
    """根据方案和周期计算订单金额（分）。"""
    plan = SUBSCRIPTION_PLANS.get(plan_type)
    if not plan or plan_type == "free":
        raise HTTPException(status_code=400, detail=f"无效方案: {plan_type}")

    monthly_price = plan["monthly_price"]  # 元
    if billing_cycle == "yearly":
        amount_yuan = monthly_price * 12 * 0.8  # 年付 8 折
    elif billing_cycle == "monthly":
        amount_yuan = monthly_price
    else:
        raise HTTPException(status_code=400, detail=f"无效周期: {billing_cycle}")
    return int(amount_yuan * 100)


@router.post("/orders", response_model=OrderResponse)
def create_order(req: CreateOrderRequest, request: Request):
    """创建订单（生成支付宝支付链接）。"""
    user_id = getattr(request.state, "user_id", "default_user")
    if user_id == "default_user":
        raise HTTPException(status_code=401, detail="请先登录")

    if req.plan_type == "free":
        raise HTTPException(status_code=400, detail="免费版无需购买")

    amount = _compute_order_amount(req.plan_type, req.billing_cycle)

    db_session = DatabaseManager.get_instance().get_session()
    try:
        order_repo = OrderRepo(db_session)
        order = order_repo.create(
            user_id=user_id,
            plan_type=req.plan_type,
            billing_cycle=req.billing_cycle,
            amount=amount,
        )

        # 调支付宝创建支付链接
        alipay = get_alipay_client()
        if alipay.config.is_configured():
            try:
                plan_name = SUBSCRIPTION_PLANS[req.plan_type]["name"]
                cycle_label = "年付" if req.billing_cycle == "yearly" else "月付"
                subject = f"金融投研AI {plan_name}{cycle_label}订阅"
                pay_url = alipay.create_pc_pay_url(
                    order_no=order.order_no,
                    amount=f"{amount / 100:.2f}",
                    subject=subject,
                )
                order_repo.set_qr_code(order.id, pay_url)
                qr_code_url = pay_url
            except Exception as e:
                logger.exception(f"生成支付链接失败: {e}")
                qr_code_url = ""  # 失败时为空，前端提示"支付暂不可用"
        else:
            logger.warning("支付宝未配置，返回空支付链接（开发模式）")
            qr_code_url = ""

    finally:
        db_session.close()

    # 重新查询以获取最新 qr_code_url
    db_session = DatabaseManager.get_instance().get_session()
    try:
        order = OrderRepo(db_session).get_by_id(order.id)
        return OrderResponse(**order.to_dict())
    finally:
        db_session.close()


@router.get("/orders", response_model=List[OrderResponse])
def list_my_orders(
    request: Request,
    status: Optional[str] = Query(None, description="pending / paid / cancelled / refunded"),
    limit: int = Query(50, le=200),
):
    """我的订单列表。"""
    user_id = getattr(request.state, "user_id", "default_user")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        orders = OrderRepo(db_session).list_by_user(user_id, status=status, limit=limit)
        return [OrderResponse(**o.to_dict()) for o in orders]
    finally:
        db_session.close()


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, request: Request):
    """订单详情（前端轮询用）。"""
    user_id = getattr(request.state, "user_id", "default_user")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        order = OrderRepo(db_session).get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问该订单")
        return OrderResponse(**order.to_dict())
    finally:
        db_session.close()


@router.post("/orders/{order_id}/mock-pay")
def mock_pay_order(order_id: str, request: Request):
    """开发模式：模拟支付成功（绕过支付宝回调）。

    ⚠️ 仅在 ALIPAY_DEBUG=true 时可用，方便本地测试订单/订阅链路。
    """
    if not os.getenv("ALIPAY_DEBUG", "true").lower() == "true":
        raise HTTPException(status_code=403, detail="生产环境禁用 mock-pay")

    user_id = getattr(request.state, "user_id", "default_user")
    if user_id == "default_user":
        raise HTTPException(status_code=401, detail="请先登录")

    db_session = DatabaseManager.get_instance().get_session()
    try:
        order_repo = OrderRepo(db_session)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问该订单")
        if order.status == "paid":
            return {"ok": True, "status": "paid", "message": "订单已是 paid"}
        if order.status != "pending":
            raise HTTPException(status_code=400, detail=f"订单状态 {order.status} 不可 mock")

        # 1. 标记支付
        order_repo.mark_paid(order.order_no, transaction_id=f"MOCK_{order.order_no}")

        # 2. 激活订阅
        sub_service = SubscriptionService(db_session)
        sub_service.activate(
            user_id=order.user_id,
            plan_type=order.plan_type,
            billing_cycle=order.billing_cycle,
            order_no=order.order_no,
        )

        logger.info(f"[MOCK] Order paid + subscription activated: {order.order_no}")
        return {
            "ok": True,
            "status": "paid",
            "message": "模拟支付成功，订阅已激活",
        }
    finally:
        db_session.close()


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, request: Request):
    """取消未支付订单。"""
    user_id = getattr(request.state, "user_id", "default_user")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        order_repo = OrderRepo(db_session)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问该订单")
        if order.status != "pending":
            raise HTTPException(status_code=400, detail=f"订单状态 {order.status} 不可取消")
        order = order_repo.cancel(order_id, user_id)
        return {"ok": True, "status": order.status}
    finally:
        db_session.close()


@router.post("/orders/{order_id}/refresh")
def refresh_order_status(order_id: str, request: Request):
    """主动查询支付宝订单状态（兜底：关闭页面后 5 分钟内手动刷）。"""
    user_id = getattr(request.state, "user_id", "default_user")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        order = OrderRepo(db_session).get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问该订单")
        if order.status != "pending":
            return {"status": order.status, "message": f"订单已{order.status}"}

        alipay = get_alipay_client()
        if not alipay.config.is_configured():
            return {"status": "pending", "message": "支付宝未配置"}

        try:
            result = alipay.query_order(order.order_no)
            if result.get("tradeStatus") == "TRADE_SUCCESS":
                # 激活订阅
                sub_service = SubscriptionService(db_session)
                sub_service.activate(
                    user_id=order.user_id,
                    plan_type=order.plan_type,
                    billing_cycle=order.billing_cycle,
                    order_no=order.order_no,
                )
                order_repo = OrderRepo(db_session)
                order = order_repo.mark_paid(order.order_no, result.get("tradeNo", ""))
                return {"status": "paid", "message": "支付成功"}
        except Exception as e:
            logger.exception(f"查询订单失败: {e}")
            return {"status": "pending", "message": f"查询失败: {e}"}

        return {"status": "pending", "message": "未支付"}
    finally:
        db_session.close()


# ============== 订阅 ==============

@router.get("/subscription/current", response_model=SubscriptionResponse)
def get_current_subscription(request: Request):
    """获取当前活跃订阅。"""
    user_id = getattr(request.state, "user_id", "default_user")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        sub_repo = SubscriptionRepo(db_session)
        sub = sub_repo.get_current(user_id)
        if not sub:
            raise HTTPException(status_code=404, detail="无活跃订阅")
        return SubscriptionResponse(
            plan_type=sub.plan_type,
            billing_cycle=sub.billing_cycle,
            status=sub.status,
            expires_at=sub.expires_at.isoformat() if sub.expires_at else "",
            auto_renew=bool(sub.auto_renew),
            started_at=sub.started_at.isoformat() if sub.started_at else "",
        )
    finally:
        db_session.close()


@router.post("/subscription/cancel")
def cancel_subscription(request: Request):
    """取消订阅（关闭自动续费 + 立即降级到 free）。"""
    user_id = getattr(request.state, "user_id", "default_user")
    if user_id == "default_user":
        raise HTTPException(status_code=401, detail="请先登录")
    db_session = DatabaseManager.get_instance().get_session()
    try:
        sub_service = SubscriptionService(db_session)
        user = sub_service.cancel(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="无活跃订阅")
        return {
            "ok": True,
            "plan_type": user.plan_type,
            "message": "已取消订阅",
        }
    finally:
        db_session.close()


# ============== 支付回调 ==============

@router.post("/callback/alipay")
async def alipay_notify(request: Request):
    """支付宝异步通知（无需鉴权 + 验签）。"""
    data = await request.form()
    data_dict = dict(data)

    alipay = get_alipay_client()
    if not alipay.verify_notify(data_dict):
        logger.warning(f"支付宝通知验签失败: {data_dict}")
        return JSONResponse(content="fail", status_code=400)

    order_no = data_dict.get("out_trade_no")
    trade_status = data_dict.get("trade_status")
    trade_no = data_dict.get("trade_no", "")

    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return "success"  # 收到非成功通知也返回 success，避免支付宝重复推送

    db_session = DatabaseManager.get_instance().get_session()
    try:
        order_repo = OrderRepo(db_session)
        order = order_repo.get_by_order_no(order_no)
        if not order:
            logger.error(f"订单不存在: {order_no}")
            return "fail"

        if order.status == "paid":
            logger.info(f"订单已处理，跳过: {order_no}")
            return "success"

        # 1. 标记订单已支付
        order_repo.mark_paid(order_no, trade_no)

        # 2. 激活订阅
        sub_service = SubscriptionService(db_session)
        sub_service.activate(
            user_id=order.user_id,
            plan_type=order.plan_type,
            billing_cycle=order.billing_cycle,
            order_no=order_no,
        )

        logger.info(f"支付成功回调处理完成: {order_no} user={order.user_id}")
        return "success"
    except Exception as e:
        logger.exception(f"处理支付回调失败: {e}")
        return "fail"
    finally:
        db_session.close()
