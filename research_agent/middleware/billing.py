"""计费中间件 —— before_agent 检查配额，after_agent 扣减用量。"""

import logging
from typing import Dict, Any
from db.database import DatabaseManager
from billing.quota_manager import QuotaManager, QuotaExceededError

logger = logging.getLogger(__name__)


async def billing_before_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """before_agent 阶段：检查配额是否充足。

    在 PlannerAgent 执行前检查，拦截超额请求。
    """
    user_id = state.get("user_id", "default_user")
    plan_type = state.get("plan_type", "free")
    report_type = state.get("report_type", "")

    # 非报告生成场景（greeting/clarification）不检查配额
    intent = state.get("intent", "task")
    if intent in ("greeting", "clarification"):
        return state

    db = DatabaseManager.get_instance()
    session = db.get_session()
    try:
        quota = QuotaManager(session)
        can_generate, msg = quota.check_report_quota(user_id, plan_type)
        if not can_generate:
            raise QuotaExceededError(msg, 0, 0)
    finally:
        session.close()

    return state


async def billing_after_agent(state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """after_agent 阶段：扣减用量。

    在报告成功生成后记录用量数据。
    """
    user_id = state.get("user_id", "default_user")
    final_answer = result.get("final_answer", "")

    # 只有成功生成报告才扣减
    if not final_answer or len(final_answer) < 100:
        return result

    report_id = result.get("report_id", "")
    intent = state.get("intent", "task")

    if intent not in ("greeting", "clarification"):
        db = DatabaseManager.get_instance()
        session = db.get_session()
        try:
            quota = QuotaManager(session)
            quota.record_report(user_id, report_id)

            # 估算 Token 消耗（中文字符约每字符 0.5 token）
            estimated_tokens = len(final_answer) // 2
            quota.record_tokens(user_id, estimated_tokens, report_id)

            logger.info(f"用量已记录: user={user_id}, report={report_id}, tokens≈{estimated_tokens}")
        except Exception as e:
            logger.error(f"用量记录失败: {e}")
        finally:
            session.close()

    return result
