"""记忆中间件 - 将对话历史集成到记忆系统。

参考 DeerFlow 的 MemoryMiddleware 设计，将研究 Agent 的对话
通过中间件形式集成到已有的 MemoryUpdateQueue 系统中。

功能：
1. 在 Agent 执行后（after_agent）提取对话
2. 过滤无关内容（工具调用结果等）
3. 检测 correction/reinforcement 信号
4. 异步更新记忆，不阻塞主流程
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)


def _filter_messages_for_memory(messages: list[BaseMessage]) -> list[BaseMessage]:
    """过滤消息，保留用户输入和最终 AI 回复。

    过滤规则：
    1. 只保留 HumanMessage（用户输入）
    2. 只保留最终 AIMessage（不含 tool_calls）
    3. 移除中间的工具调用和 ToolMessage

    Args:
        messages: 原始消息列表

    Returns:
        过滤后的消息列表
    """
    if not messages:
        return []

    filtered = []
    last_ai_idx = -1

    for i, msg in enumerate(messages):
        msg_type = getattr(msg, "type", None)

        # 保留用户消息
        if msg_type == "human":
            filtered.append(msg)

        # 保留最终的 AI 消息（不含 tool_calls）
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                filtered.append(msg)
                last_ai_idx = i

    return filtered


def _detect_correction(messages: list[BaseMessage]) -> bool:
    """检测用户是否在纠正 AI 的错误。

    通过检测用户消息中是否包含纠正性关键词来判断。

    Args:
        messages: 消息列表

    Returns:
        是否检测到纠正
    """
    correction_keywords = [
        "不对", "不是", "错误", "错了", "纠正",
        "更正", "修正", "实际上", "其实",
        "不是的", "不对的", "你搞错了",
        "wrong", "incorrect", "actually",
    ]

    for msg in messages:
        if not isinstance(msg, HumanMessage):
            continue

        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

        content_lower = content.lower()
        for keyword in correction_keywords:
            if keyword in content_lower:
                logger.info(f"检测到纠正信号: 关键词 '{keyword}'")
                return True

    return False


def _detect_reinforcement(messages: list[BaseMessage]) -> bool:
    """检测用户是否在强化/确认 AI 的回答。

    Args:
        messages: 消息列表

    Returns:
        是否检测到强化
    """
    reinforcement_keywords = [
        "对", "是的", "没错", "正确", "很好",
        "明白了", "了解了", "好的", "ok", "okay",
        "right", "correct", "yes", "good",
    ]

    has_user = False
    has_ai = False

    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            has_user = True
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            content_lower = content.lower()
            for keyword in reinforcement_keywords:
                if keyword in content_lower:
                    return True
        elif msg_type == "ai":
            has_ai = True

    return False


class MemoryMiddleware(BaseMiddleware):
    """记忆中间件。

    集成研究 Agent 的对话到已有的 MemoryUpdateQueue 系统。

    工作流程：
    1. Agent 执行完成后（after_agent），获取消息列表
    2. 过滤消息（只保留用户输入和最终 AI 回复）
    3. 检测 correction/reinforcement 信号
    4. 将对话上下文加入 MemoryUpdateQueue
    5. 队列会在 debounce_seconds 后异步处理

    配置参数：
    - memory_queue: MemoryUpdateQueue 实例
    - enabled: 是否启用
    - min_messages: 最少消息数量（默认 2）
    - user_id_extractor: 从 runtime 提取 user_id 的函数
    """

    name: str = "memory"
    description: str = "将对话历史集成到记忆系统"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 50,  # after_agent 阶段，较晚执行
        min_messages: int = 2,
        user_id_extractor: Any = None,
    ):
        """初始化记忆中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            min_messages: 最少消息数量
            user_id_extractor: user_id 提取函数
        """
        super().__init__(enabled=enabled, order=order)
        self.min_messages = min_messages
        self.user_id_extractor = user_id_extractor or (lambda runtime: runtime.get("user_id", "default"))

    def _get_thread_id(self, runtime: dict[str, Any]) -> str:
        """获取线程 ID。"""
        return runtime.get("thread_id", "default")

    def _get_user_id(self, runtime: dict[str, Any]) -> str:
        """获取用户 ID。"""
        if callable(self.user_id_extractor):
            return self.user_id_extractor(runtime)
        return self.user_id_extractor

    async def after_agent(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """Agent 执行后，提取对话并加入记忆队列。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult（通常为 None，不修改状态）
        """
        messages = state.get("messages", [])

        if not messages:
            logger.debug("无消息，跳过记忆更新")
            return None

        # 过滤消息
        filtered_messages = _filter_messages_for_memory(messages)

        # 检查是否有足够的有效消息
        user_messages = [m for m in filtered_messages if isinstance(m, HumanMessage)]
        ai_messages = [m for m in filtered_messages if isinstance(m, AIMessage)]

        if len(user_messages) < 1 or len(ai_messages) < 1:
            logger.debug(
                f"消息不足，跳过记忆更新: "
                f"user={len(user_messages)}, ai={len(ai_messages)}"
            )
            return None

        # 检测信号
        correction_detected = _detect_correction(filtered_messages)
        reinforcement_detected = not correction_detected and _detect_reinforcement(filtered_messages)

        # 获取线程 ID 和用户 ID
        thread_id = self._get_thread_id(runtime)
        user_id = self._get_user_id(runtime)

        # 获取 MemoryUpdateQueue 并添加
        try:
            from memory.queue import get_memory_queue
            memory_queue = get_memory_queue()

            memory_queue.add(
                thread_id=thread_id,
                messages=filtered_messages,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )

            logger.info(
                f"记忆更新已加入队列: thread={thread_id}, "
                f"messages={len(filtered_messages)}, "
                f"correction={correction_detected}, "
                f"reinforcement={reinforcement_detected}"
            )

        except Exception as e:
            logger.exception(f"将对话加入记忆队列失败: {e}")

        return None


class MemoryInjectionMiddleware(BaseMiddleware):
    """记忆注入中间件。

    在 Agent 执行前，将记忆上下文注入到状态中。

    功能：
    1. 从记忆系统读取当前线程的记忆
    2. 注入到状态的 memory_context 字段
    3. 让 Agent 能够感知之前的对话上下文
    """

    name: str = "memory_injection"
    description: str = "将记忆上下文注入到 Agent 状态"

    def __init__(
        self,
        enabled: bool = True,
        order: int = -10,  # before_model 阶段，较早执行
        max_injection_tokens: int = 2000,
        memory_key: str = "memory_context",
    ):
        """初始化记忆注入中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            max_injection_tokens: 最大注入 token 数
            memory_key: 记忆注入的状态键名
        """
        super().__init__(enabled=enabled, order=order)
        self.max_injection_tokens = max_injection_tokens
        self.memory_key = memory_key

    def _get_thread_id(self, runtime: dict[str, Any]) -> str:
        """获取线程 ID。"""
        return runtime.get("thread_id", "default")

    def _get_user_id(self, runtime: dict[str, Any]) -> str:
        """获取用户 ID。"""
        return runtime.get("user_id", "default")

    def _load_memory_context(self, thread_id: str, user_id: str) -> str:
        """加载记忆上下文。"""
        try:
            from memory.storage import FileMemoryStorage

            storage = FileMemoryStorage()
            memory_data = storage.load_memory(user_id=user_id, agent_name="research")

            if not memory_data:
                return ""

            # 格式化记忆上下文
            context_parts = []

            # 工作上下文
            if memory_data.get("workContext"):
                context_parts.append(f"工作背景: {memory_data['workContext']}")

            # 近期上下文
            if memory_data.get("recentMonths"):
                context_parts.append(f"近期情况: {memory_data['recentMonths']}")

            # 重要事实
            facts = memory_data.get("facts", [])
            if facts:
                fact_texts = [f["content"] for f in facts[:10]]
                context_parts.append(f"重要信息: {'; '.join(fact_texts)}")

            if context_parts:
                return "\n\n".join(context_parts)

            return ""

        except Exception as e:
            logger.exception(f"加载记忆上下文失败: {e}")
            return ""

    async def before_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用前注入记忆上下文。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            包含记忆上下文的 MiddlewareResult
        """
        thread_id = self._get_thread_id(runtime)
        user_id = self._get_user_id(runtime)

        memory_context = self._load_memory_context(thread_id, user_id)

        if not memory_context:
            return None

        # 简单截断（实际应该按 token 计算）
        if len(memory_context) > self.max_injection_tokens * 4:
            memory_context = memory_context[:self.max_injection_tokens * 4] + "..."

        logger.debug(f"注入记忆上下文: thread={thread_id}, length={len(memory_context)}")

        return MiddlewareResult.updated({self.memory_key: memory_context})
