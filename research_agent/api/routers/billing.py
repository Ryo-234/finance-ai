"""计费 API 路由 —— 方案查询、用量统计。"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List

from billing.plans import SUBSCRIPTION_PLANS, get_plan_limits
from billing.quota_manager import QuotaManager
from db.database import DatabaseManager

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlanInfo(BaseModel):
    plan_type: str
    name: str
    monthly_price: int
    monthly_reports: int  # -1 表示无限
    max_tokens_per_month: int
    features: List[str]


class UsageInfo(BaseModel):
    reports_this_month: int
    tokens_this_month: int
    report_limit: int  # -1 表示无限
    token_limit: int
    daily_stats: list


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
