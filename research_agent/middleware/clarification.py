"""澄清中间件 - 拦截 ask_clarification 工具调用并中断执行。

当模型调用 ask_clarification 工具时：
1. 拦截工具调用
2. 提取澄清问题和选项
3. 格式化为用户友好的消息
4. 返回 Command(goto=END) 中断执行
5. 等待用户回复后再继续
"""

import json
import logging
from hashlib import sha256
from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)


class ClarificationMiddleware(BaseMiddleware):
    """拦截澄清请求并呈现给用户。

    当模型调用 ask_clarification 工具时：
    1. 拦截工具调用（不执行原始工具代码）
    2. 提取澄清问题和元数据
    3. 格式化为用户友好的消息
    4. 返回 Command(goto=END) 中断执行
    5. 等待用户回复后再继续
    """

    name: str = "clarification"
    description: str = "拦截澄清请求并中断执行呈现给用户"

    def __init__(self, enabled: bool = True, order: int = -100):
        """初始化澄清中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序（很早就执行，在其他中间件之前拦截）
        """
        super().__init__(enabled=enabled, order=order)

    def _stable_message_id(self, tool_call_id: str, formatted_message: str) -> str:
        """生成稳定的确认消息 ID。

        确保重试的确认调用会替换而不是追加。
        """
        if tool_call_id:
            return f"clarification:{tool_call_id}"
        digest = sha256(formatted_message.encode("utf-8")).hexdigest()[:16]
        return f"clarification:{digest}"

    def _format_clarification_message(self, args: dict) -> str:
        """将澄清参数格式化为用户友好的消息。

        Args:
            args: 工具调用参数

        Returns:
            格式化后的消息字符串
        """
        question = args.get("question", "")
        clarification_type = args.get("clarification_type", "missing_info")
        context = args.get("context")
        options = args.get("options", [])

        # 处理某些模型将数组序列化为字符串的情况
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [options]

        if options is None:
            options = []
        elif not isinstance(options, list):
            options = [options]

        # 类型对应的图标
        type_icons = {
            "missing_info": "❓",
            "ambiguous_requirement": "🤔",
            "approach_choice": "🔀",
            "risk_confirmation": "⚠️",
            "suggestion": "💡",
        }

        icon = type_icons.get(clarification_type, "❓")

        # 构建消息
        message_parts = []

        # 先添加背景（如果有的话）
        if context:
            message_parts.append(f"{icon} {context}")
            message_parts.append(f"\n{question}")
        else:
            message_parts.append(f"{icon} {question}")

        # 添加选项
        if options and len(options) > 0:
            message_parts.append("")
            for i, option in enumerate(options, 1):
                message_parts.append(f"  {i}. {option}")

        return "\n".join(message_parts)

    def _is_clarification_call(self, state: dict[str, Any]) -> tuple[bool, dict | None]:
        """检查状态中是否有 ask_clarification 工具调用。

        Args:
            state: 当前状态

        Returns:
            (是否是澄清调用, 工具调用参数)
        """
        messages = state.get("messages", [])
        if not messages:
            return False, None

        last_msg = messages[-1]

        # 检查是否是 AIMessage 且有工具调用
        msg_type = getattr(last_msg, "type", None)
        if msg_type != "ai":
            return False, None

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return False, None

        # 查找 ask_clarification 调用
        for tc in tool_calls:
            if tc.get("name") == "ask_clarification":
                return True, tc.get("args", {})

        return False, None

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult | None:
        """在模型调用后检查是否需要拦截澄清请求。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            如果是澄清调用，返回中断结果；否则返回 None
        """
        is_clarify, args = self._is_clarification_call(state)

        if not is_clarify:
            return None

        logger.info("拦截到澄清请求")

        # 格式化消息
        formatted_message = self._format_clarification_message(args)

        # 获取 tool_call_id
        messages = state.get("messages", [])
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None)

        tool_call_id = ""
        if tool_calls:
            for tc in tool_calls:
                if tc.get("name") == "ask_clarification":
                    tool_call_id = tc.get("id", "")
                    break

        # 创建确认消息
        confirm_message = HumanMessage(
            content=formatted_message,
            name="clarification",
        )

        # 清除 tool_calls 以避免重复执行
        # 创建更新的消息列表
        updated_messages = []
        for msg in messages[:-1]:
            updated_messages.append(msg)

        # 用无 tool_calls 的版本替换最后一条消息
        import copy
        last_msg_copy = copy.copy(last_msg)
        last_msg_copy.tool_calls = []
        last_msg_copy.additional_kwargs = {}
        updated_messages.append(last_msg_copy)

        # 添加确认消息
        updated_messages.append(confirm_message)

        logger.info("澄清消息已格式化，执行中断")

        return MiddlewareResult(
            updates={"messages": updated_messages},
            stop=True,  # 中断执行
        )

    def wrap_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[..., Any],
        runtime: dict[str, Any] | None = None,
    ) -> Any:
        """包装工具调用，拦截 ask_clarification。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            handler: 原始工具执行处理器
            runtime: 运行时上下文

        Returns:
            工具执行结果或中断命令
        """
        # 如果是 ask_clarification，不执行工具，直接返回
        # 注意：由于 after_model 已经处理了，这里通常不会走到
        # 但保留作为额外保护
        if tool_name == "ask_clarification":
            logger.info("拦截 ask_clarification 工具调用")
            return "Clarification request intercepted by middleware"

        return handler()

    async def wrap_tool_call_async(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[..., Any],
        runtime: dict[str, Any] | None = None,
    ) -> Any:
        """异步包装工具调用，拦截 ask_clarification。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            handler: 原始工具执行处理器
            runtime: 运行时上下文

        Returns:
            工具执行结果或中断命令
        """
        if tool_name == "ask_clarification":
            logger.info("拦截 ask_clarification 工具调用（异步）")
            return "Clarification request intercepted by middleware"

        return await handler()
