"""合规中间件 —— 在 after_agent 阶段自动注入声明和拦截违规内容。"""

import logging
from typing import Dict, Any
from compliance.checker import ComplianceChecker
from compliance.disclaimers import DisclaimerManager

logger = logging.getLogger(__name__)

_checker = ComplianceChecker()
_disclaimer_manager = DisclaimerManager()


async def compliance_after_agent(state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """after_agent 阶段：合规检查与声明注入。

    在 Synthesizer 完成后自动执行：
    1. 注入 AI 标识和免责声明
    2. 执行合规检查
    3. 记录合规状态
    """
    final_answer = result.get("final_answer", "")
    report_type = state.get("report_type", "default")

    if not final_answer:
        # greeting/clarification 场景不需要合规注入
        result["compliance_checked"] = True
        return result

    # 1. 注入合规声明
    injected = _disclaimer_manager.inject(final_answer, report_type)
    if injected != final_answer:
        result["final_answer"] = injected
        logger.info("合规声明已注入")

    # 2. 执行合规检查
    sources = result.get("sources", [])
    check_result = _checker.check(injected, sources=sources, report_type=report_type)

    if not check_result["passed"]:
        logger.warning(f"合规检查未通过: {check_result['violations']}")
        # 追加合规警告（但不阻止输出）
        result["final_answer"] = f"{injected}\n\n---\n\n> ⚠️ 合规提示：{'; '.join(check_result['violations'])}"

    result["compliance_checked"] = check_result["passed"]
    result["compliance_score"] = check_result["score"]

    return result
