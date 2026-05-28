"""上下文压缩中间件 - 当对话历史接近 token 限制时自动压缩。

参考 DeerFlow 的 SummarizationMiddleware 设计，提供：
1. 基于 token 数量的触发条件
2. 保留最近消息策略
3. 将旧消息压缩成摘要
4. 摘要注入到对话历史

该中间件是 P0 级别功能，防止对话超出模型上下文窗口。
"""

import logging
import threading
from copy import deepcopy
from typing import Any, Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_TOKEN_LIMIT = 6000  # 触发压缩的 token 阈值
_DEFAULT_KEEP_MESSAGES = 10  # 压缩后保留的最近消息数
_DEFAULT_SUMMARY_PROMPT = """请总结以下对话的要点，保留关键信息和重要结论。

对话记录：
{content}

请用简洁的语言总结："""

_SUMMARIZED_MSG = "以下是对之前对话的摘要：\n\n{summary}"


def _estimate_token_count(messages: list[BaseMessage]) -> int:
    """粗略估算消息列表的 token 数量。

    使用简单公式：中文 ~2 字符/token，英文 ~4 字符/token。

    Args:
        messages: 消息列表

    Returns:
        估算的 token 数量
    """
    total = 0
    for msg in messages:
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        # 简单估算：中文按 2 字符/token，英文按 4 字符/token
        chinese_chars = sum(1 for c in content if '一' <= c <= '鿿')
        other_chars = len(content) - chinese_chars
        total += chinese_chars // 2 + other_chars // 4
        # 消息类型 overhead
        total += 10
    return total


class SummarizationMiddleware(BaseMiddleware):
    """上下文压缩中间件。

    功能：
    1. 在 before_model 阶段检测是否需要压缩
    2. 当 token 数量超过阈值时，触发压缩
    3. 将旧消息压缩成摘要，保留最近的消息
    4. 在摘要消息中注入压缩后的上下文

    配置参数：
    - token_limit: 触发压缩的 token 阈值（默认 6000）
    - keep_messages: 压缩后保留的最近消息数（默认 10）
    - summary_provider: 生成摘要的函数（默认使用本地模板）
    - summary_prompt: 摘要提示词模板
    """

    name: str = "summarization"
    description: str = "当对话历史接近 token 限制时自动压缩上下文"

    def __init__(
        self,
        enabled: bool = True,
        order: int = -5,  # before_model 阶段，很早执行
        token_limit: int = _DEFAULT_TOKEN_LIMIT,
        keep_messages: int = _DEFAULT_KEEP_MESSAGES,
        summary_provider: Callable[[list[BaseMessage]], str] | None = None,
        summary_prompt: str = _DEFAULT_SUMMARY_PROMPT,
    ):
        """初始化上下文压缩中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            token_limit: 触发压缩的 token 阈值
            keep_messages: 压缩后保留的最近消息数
            summary_provider: 摘要生成函数
            summary_prompt: 摘要提示词模板
        """
        super().__init__(enabled=enabled, order=order)
        self.token_limit = token_limit
        self.keep_messages = keep_messages
        self.summary_provider = summary_provider
        self.summary_prompt = summary_prompt

        # 跟踪已压缩的次数（用于日志）
        self._compression_count: dict[str, int] = {}
        self._lock = threading.Lock()

    def _get_thread_id(self, runtime: dict[str, Any]) -> str:
        """获取线程 ID。"""
        return runtime.get("thread_id", "default")

    def _should_summarize(self, messages: list[BaseMessage]) -> bool:
        """判断是否需要压缩。

        Args:
            messages: 消息列表

        Returns:
            是否需要压缩
        """
        token_count = _estimate_token_count(messages)
        return token_count >= self.token_limit

    def _partition_messages(
        self, messages: list[BaseMessage]
    ) -> tuple[list[BaseMessage], list[BaseMessage]]:
        """分割消息，保留最近的消息。

        Args:
            messages: 消息列表

        Returns:
            (待压缩消息, 保留消息)
        """
        if len(messages) <= self.keep_messages:
            return [], messages

        return messages[:-self.keep_messages], messages[-self.keep_messages:]

    def _create_summary_content(self, messages: list[BaseMessage]) -> str:
        """创建摘要内容。

        Args:
            messages: 待压缩的消息列表

        Returns:
            摘要文本
        """
        # 格式化消息内容
        content_parts = []
        for msg in messages:
            msg_type = getattr(msg, "type", "unknown")
            name = getattr(msg, "name", "user")

            msg_content = getattr(msg, "content", "") or ""
            if isinstance(msg_content, list):
                msg_content = "\n".join(
                    block.get("text", "") for block in msg_content
                    if isinstance(block, dict) and block.get("type") == "text"
                )

            if isinstance(msg, HumanMessage):
                content_parts.append(f"用户: {msg_content}")
            elif isinstance(msg, AIMessage):
                content_parts.append(f"助手: {msg_content}")
            elif isinstance(msg, SystemMessage):
                content_parts.append(f"系统: {msg_content}")
            else:
                content_parts.append(f"{name}: {msg_content}")

        content = "\n\n".join(content_parts)

        # 如果有自定义摘要提供者，使用它
        if self.summary_provider:
            try:
                return self.summary_provider(messages)
            except Exception as e:
                logger.exception(f"摘要生成失败: {e}")

        # 否则使用简单模板
        if len(content) > self.token_limit * 3:
            # 内容过长，截断
            content = content[: self.token_limit * 3] + "..."

        return content

    def _build_summary_message(self, summary: str) -> HumanMessage:
        """构建摘要消息。

        Args:
            summary: 摘要内容

        Returns:
            摘要 HumanMessage
        """
        content = _SUMMARIZED_MSG.format(summary=summary)
        return HumanMessage(content=content, name="summary")

    async def before_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用前检测是否需要压缩。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 检查是否需要压缩
        if not self._should_summarize(messages):
            return None

        # 分割消息
        to_summarize, to_keep = self._partition_messages(messages)

        if not to_summarize:
            return None

        thread_id = self._get_thread_id(runtime)

        # 更新压缩计数
        with self._lock:
            self._compression_count[thread_id] = self._compression_count.get(thread_id, 0) + 1
            compression_num = self._compression_count[thread_id]

        # 创建摘要
        summary_content = self._create_summary_content(to_summarize)
        summary_msg = self._build_summary_message(summary_content)

        logger.info(
            f"上下文压缩触发: thread={thread_id}, "
            f"压缩第 {compression_num} 次, "
            f"待压缩消息={len(to_summarize)}, "
            f"保留消息={len(to_keep)}"
        )

        # 构建新的消息列表
        # 使用 RemoveMessage 移除旧消息，然后添加摘要和保留的消息
        new_messages = [
            RemoveMessage(id=msg.id) for msg in to_summarize
        ]
        new_messages.append(summary_msg)
        new_messages.extend(to_keep)

        return MiddlewareResult.updated({"messages": new_messages})


class ContextCompressionMiddleware(BaseMiddleware):
    """上下文压缩中间件（别名）。

    提供基于 token 计数器的上下文压缩，简单的保留策略。
    适用于资源受限的场景。
    """

    name: str = "context_compression"
    description: str = "简单的上下文压缩，保留最近的固定数量消息"

    def __init__(
        self,
        enabled: bool = True,
        order: int = -5,
        max_messages: int = 20,  # 最大保留消息数
    ):
        """初始化上下文压缩中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            max_messages: 最大保留消息数
        """
        super().__init__(enabled=enabled, order=order)
        self.max_messages = max_messages

    async def before_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用前压缩上下文。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 检查是否超出限制
        if len(messages) <= self.max_messages:
            return None

        thread_id = runtime.get("thread_id", "default")

        # 保留系统消息和最近的消息
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        other_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]

        # 保留最近的消息
        to_compress = other_messages[:-self.max_messages]
        to_keep = other_messages[-self.max_messages:]

        if not to_compress:
            return None

        logger.info(
            f"上下文压缩: thread={thread_id}, "
            f"压缩消息={len(to_compress)}, "
            f"保留消息={len(to_keep)}"
        )

        # 创建压缩摘要
        summary_parts = []
        for msg in to_compress[-5:]:  # 只取最后5条作为摘要
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if content:
                msg_type = type(msg).__name__
                summary_parts.append(f"[{msg_type}] {content[:100]}...")

        summary_content = f"[已压缩 {len(to_compress)} 条消息]\n\n" + "\n\n".join(summary_parts)
        summary_msg = HumanMessage(content=summary_content, name="compression_summary")

        # 构建新消息列表
        new_messages = system_messages + [summary_msg] + to_keep

        return MiddlewareResult.updated({"messages": new_messages})