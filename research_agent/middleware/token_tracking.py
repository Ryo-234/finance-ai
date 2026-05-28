"""Token 追踪中间件 - 跟踪和记录 Agent 执行过程中的 Token 使用量。

功能：
1. 跟踪每次模型调用的 Token 使用量
2. 计算累计 Token 使用量
3. 在接近上下文限制时发出警告
4. 记录详细的 Token 使用日志

该中间件用于：
- 成本控制和分析
- 上下文窗口管理
- 性能监控
"""

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional

from langchain_core.messages import AIMessage

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_WARNING_THRESHOLD = 0.8  # 警告阈值（80%）
_DEFAULT_CRITICAL_THRESHOLD = 0.95  # 严重警告阈值（95%）
_DEFAULT_CONTEXT_LIMIT = 128000  # 默认上下文限制（GPT-4）

# 警告消息
_TOKEN_WARNING_MSG = "[TOKEN WARNING] Token 使用已达 {current}/{limit} ({percentage:.0%})，建议压缩上下文。"
_TOKEN_CRITICAL_MSG = "[TOKEN CRITICAL] Token 使用接近限制 {current}/{limit} ({percentage:.0%})，上下文即将溢出！"


@dataclass
class TokenUsage:
    """单次 Token 使用记录。"""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str = "unknown"
    thread_id: str = "default"


@dataclass
class TokenStats:
    """Token 使用统计。"""

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0
    first_request_time: Optional[datetime] = None
    last_request_time: Optional[datetime] = None
    by_model: dict[str, TokenUsage] = field(default_factory=dict)


class TokenTrackingMiddleware(BaseMiddleware):
    """Token 追踪中间件。

    功能：
    1. 跟踪每次 LLM 调用的 Token 使用量
    2. 记录详细的使用日志
    3. 在接近限制时发出警告

    配置参数：
    - context_limit: 上下文窗口限制
    - warning_threshold: 警告阈值（默认 80%）
    - critical_threshold: 严重警告阈值（默认 95%）
    - track_per_thread: 是否按线程跟踪
    - log_usage: 是否记录详细日志
    """

    name: str = "token_tracking"
    description: str = "追踪 Agent 执行过程中的 Token 使用量"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 20,  # after_model 阶段
        context_limit: int = _DEFAULT_CONTEXT_LIMIT,
        warning_threshold: float = _DEFAULT_WARNING_THRESHOLD,
        critical_threshold: float = _DEFAULT_CRITICAL_THRESHOLD,
        track_per_thread: bool = True,
        log_usage: bool = True,
    ):
        """初始化 Token 追踪中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            context_limit: 上下文窗口限制（tokens）
            warning_threshold: 警告阈值（0-1）
            critical_threshold: 严重警告阈值（0-1）
            track_per_thread: 是否按线程跟踪
            log_usage: 是否记录详细日志
        """
        super().__init__(enabled=enabled, order=order)
        self.context_limit = context_limit
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.track_per_thread = track_per_thread
        self.log_usage = log_usage

        self._lock = threading.Lock()
        # 全局统计
        self._global_stats = TokenStats()
        # 按线程的统计: thread_id -> TokenStats
        self._thread_stats: dict[str, TokenStats] = defaultdict(TokenStats)

    def _get_thread_id(self, runtime: dict[str, Any]) -> str:
        """获取线程 ID。"""
        return runtime.get("thread_id", "default") if self.track_per_thread else "_global_"

    def _get_stats(self, thread_id: str) -> TokenStats:
        """获取线程的统计。"""
        return self._thread_stats[thread_id]

    def _extract_usage_from_message(self, message: AIMessage) -> Optional[dict]:
        """从 AIMessage 提取 usage 信息。

        Args:
            message: AIMessage 对象

        Returns:
            usage 字典或 None
        """
        # 尝试从 response_metadata 获取
        response_metadata = getattr(message, "response_metadata", {}) or {}

        # OpenAI 格式
        usage = response_metadata.get("usage") or {}

        if usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        # 尝试从 additional_kwargs 获取
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        usage = additional_kwargs.get("usage") or {}

        if usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return None

    def _extract_model_name(self, message: AIMessage) -> str:
        """提取模型名称。"""
        response_metadata = getattr(message, "response_metadata", {}) or {}
        model = response_metadata.get("model_name") or response_metadata.get("model")
        return model or "unknown"

    def _update_stats(self, thread_id: str, usage: dict, model_name: str) -> tuple[int, int, float]:
        """更新统计信息。

        Args:
            thread_id: 线程 ID
            usage: usage 字典
            model_name: 模型名称

        Returns:
            (当前总量, 限制, 使用比例)
        """
        stats = self._get_stats(thread_id)
        now = datetime.now(UTC)

        # 更新全局统计
        self._global_stats.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._global_stats.total_completion_tokens += usage.get("completion_tokens", 0)
        self._global_stats.total_tokens += usage.get("total_tokens", 0)
        self._global_stats.request_count += 1
        if not self._global_stats.first_request_time:
            self._global_stats.first_request_time = now
        self._global_stats.last_request_time = now

        # 更新线程统计
        stats.total_prompt_tokens += usage.get("prompt_tokens", 0)
        stats.total_completion_tokens += usage.get("completion_tokens", 0)
        stats.total_tokens += usage.get("total_tokens", 0)
        stats.request_count += 1
        if not stats.first_request_time:
            stats.first_request_time = now
        stats.last_request_time = now

        current = stats.total_tokens
        limit = self.context_limit
        percentage = current / limit if limit > 0 else 0

        return current, limit, percentage

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用后追踪 Token 使用。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult（包含警告消息如果需要）
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        # 提取 usage
        usage = self._extract_usage_from_message(last_msg)
        if not usage:
            if self.log_usage:
                logger.debug("无法从消息中提取 Token 使用量")
            return None

        model_name = self._extract_model_name(last_msg)
        thread_id = self._get_thread_id(runtime)

        # 更新统计
        current, limit, percentage = self._update_stats(thread_id, usage, model_name)

        # 记录日志
        if self.log_usage:
            logger.info(
                f"Token 使用: thread={thread_id}, "
                f"prompt={usage['prompt_tokens']}, "
                f"completion={usage['completion_tokens']}, "
                f"total={usage['total_tokens']}, "
                f"cumulative={current}/{limit} ({percentage:.0%})"
            )

        # 检查是否需要警告
        if percentage >= self.critical_threshold:
            warning_msg = _TOKEN_CRITICAL_MSG.format(
                current=current,
                limit=limit,
                percentage=percentage,
            )
            logger.warning(f"Token 严重警告: {warning_msg}")

            from langchain_core.messages import HumanMessage
            return MiddlewareResult.with_messages([
                HumanMessage(content=warning_msg, name="token_warning")
            ])

        elif percentage >= self.warning_threshold:
            warning_msg = _TOKEN_WARNING_MSG.format(
                current=current,
                limit=limit,
                percentage=percentage,
            )
            logger.info(f"Token 警告: {warning_msg}")

            from langchain_core.messages import HumanMessage
            return MiddlewareResult.with_messages([
                HumanMessage(content=warning_msg, name="token_warning")
            ])

        return None

    def get_stats(self, thread_id: str | None = None) -> dict:
        """获取 Token 使用统计。

        Args:
            thread_id: 线程 ID（None 表示全局统计）

        Returns:
            统计信息字典
        """
        with self._lock:
            if thread_id and thread_id in self._thread_stats:
                stats = self._thread_stats[thread_id]
            else:
                stats = self._global_stats

            return {
                "total_prompt_tokens": stats.total_prompt_tokens,
                "total_completion_tokens": stats.total_completion_tokens,
                "total_tokens": stats.total_tokens,
                "request_count": stats.request_count,
                "first_request_time": stats.first_request_time.isoformat() if stats.first_request_time else None,
                "last_request_time": stats.last_request_time.isoformat() if stats.last_request_time else None,
            }

    def reset_stats(self, thread_id: str | None = None) -> None:
        """重置统计信息。

        Args:
            thread_id: 线程 ID（None 表示重置所有）
        """
        with self._lock:
            if thread_id:
                if thread_id in self._thread_stats:
                    self._thread_stats[thread_id] = TokenStats()
            else:
                self._thread_stats.clear()
                self._global_stats = TokenStats()


class TokenBudgetMiddleware(BaseMiddleware):
    """Token 预算中间件。

    限制单个请求或线程的 Token 使用量。

    配置参数：
    - max_tokens_per_request: 每次请求的最大 Token 数
    - max_total_tokens: 最大累计 Token 数
    """

    name: str = "token_budget"
    description: str = "限制 Token 使用预算"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 15,
        max_tokens_per_request: int | None = None,
        max_total_tokens: int | None = None,
    ):
        """初始化 Token 预算中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            max_tokens_per_request: 每次请求最大 Token 数
            max_total_tokens: 累计最大 Token 数
        """
        super().__init__(enabled=enabled, order=order)
        self.max_tokens_per_request = max_tokens_per_request
        self.max_total_tokens = max_total_tokens

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """检查 Token 预算是否超限。"""
        # 这个功能比较复杂，需要结合 TokenTrackingMiddleware 的数据
        # 这里仅作占位实现
        return None
