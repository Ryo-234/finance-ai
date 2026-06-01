"""配额管理器 —— 检查、扣减、重置用量配额。"""

import logging
from datetime import datetime, timezone
from typing import Tuple
from sqlalchemy.orm import Session

from billing.plans import get_plan_limits
from db.repositories.usage_repo import UsageRepo

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """配额超限异常。"""

    def __init__(self, message: str, current: int, limit: int):
        super().__init__(message)
        self.current = current
        self.limit = limit


class QuotaManager:
    """配额管理器。

    负责：
    - 检查用户是否有剩余配额
    - 扣减配额（记录用量）
    - 查询当前用量
    """

    def __init__(self, session: Session):
        self.usage_repo = UsageRepo(session)

    def check_report_quota(self, user_id: str, plan_type: str = "free") -> Tuple[bool, str]:
        """检查用户是否还能生成报告。

        返回：(可用, 说明)
        """
        limits = get_plan_limits(plan_type)
        monthly_limit = limits["monthly_reports"]

        # -1 表示无限
        if monthly_limit < 0:
            return True, "无限制"

        current_count = self.usage_repo.get_monthly_report_count(user_id)
        if current_count >= monthly_limit:
            msg = f"本月报告配额已用完（{current_count}/{monthly_limit}），请升级方案或等待下月重置"
            logger.warning(f"配额超限: user={user_id}, plan={plan_type}, reports={current_count}/{monthly_limit}")
            return False, msg

        return True, f"剩余 {monthly_limit - current_count} 份报告"

    def check_token_quota(self, user_id: str, plan_type: str = "free", needed: int = 0) -> Tuple[bool, str]:
        """检查 Token 配额是否足够。

        返回：(可用, 说明)
        """
        limits = get_plan_limits(plan_type)
        token_limit = limits["max_tokens_per_month"]

        if token_limit < 0:
            return True, "无限制"

        current_usage = self.usage_repo.get_monthly_token_sum(user_id)
        if current_usage + needed > token_limit:
            msg = f"本月 Token 配额即将超限（{current_usage}/{token_limit}），请升级方案"
            logger.warning(f"Token 配额预警: user={user_id}, usage={current_usage}/{token_limit}")
            return False, msg

        return True, f"Token 剩余 {token_limit - current_usage}"

    def record_report(self, user_id: str, report_id: str) -> None:
        """记录一次报告生成。"""
        self.usage_repo.record(
            user_id=user_id,
            record_type="report_generated",
            amount=1,
            metadata={"report_id": report_id},
        )

    def record_tokens(self, user_id: str, token_count: int, report_id: str = "") -> None:
        """记录 Token 消耗。"""
        self.usage_repo.record(
            user_id=user_id,
            record_type="token_consumed",
            amount=token_count,
            metadata={"report_id": report_id} if report_id else {},
        )

    def get_current_usage(self, user_id: str) -> dict:
        """获取用户当前周期的用量概览。"""
        limits = get_plan_limits("free")  # 默认 free，实际应从 user 获取

        return {
            "reports_this_month": self.usage_repo.get_monthly_report_count(user_id),
            "tokens_this_month": self.usage_repo.get_monthly_token_sum(user_id),
            "daily_stats": self.usage_repo.get_daily_stats(user_id, days=7),
        }
