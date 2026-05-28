"""澄清工具 - 用于向用户询问澄清信息。

当用户请求模糊或缺少必要信息时，调用此工具向用户询问。
执行会被中间件拦截并中断，等待用户回复。
"""

from typing import Literal, Optional
from langchain_core.tools import tool


@tool("ask_clarification", return_direct=True)
def ask_clarification_tool(
    question: str,
    clarification_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    context: Optional[str] = None,
    options: Optional[list[str]] = None,
) -> str:
    """当需要用户更多信息才能继续时，向用户询问澄清。"""
    # 这是一个占位实现
    # 实际逻辑由 ClarificationMiddleware 拦截处理
    return "Clarification request processed by middleware"
