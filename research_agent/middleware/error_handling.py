"""错误处理中间件 - 统一处理 Agent 执行过程中的错误。

该中间件负责：
1. 捕获模型调用错误，转换为友好的错误消息
2. 捕获工具执行错误，转换为结构化错误响应
3. 防止错误中断整个流程，让 Agent 有机会恢复
"""

import logging
import traceback
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型枚举。"""

    # 模型相关错误
    MODEL_ERROR = "model_error"  # LLM 调用错误
    MODEL_RATE_LIMIT = "model_rate_limit"  # 速率限制
    MODEL_TIMEOUT = "model_timeout"  # 超时

    # 工具相关错误
    TOOL_NOT_FOUND = "tool_not_found"  # 工具不存在
    TOOL_ARGUMENT_ERROR = "tool_argument_error"  # 参数错误
    TOOL_EXECUTION_ERROR = "tool_execution_error"  # 执行错误
    TOOL_TIMEOUT = "tool_timeout"  # 超时
    TOOL_NOT_FOUND_ERROR = "tool_not_found_error"  # 工具不存在

    # Agent 流程错误
    AGENT_EXECUTION_ERROR = "agent_execution_error"  # Agent 执行错误
    STATE_UPDATE_ERROR = "state_update_error"  # 状态更新错误

    # 未知错误
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorInfo:
    """错误信息结构。"""

    error_type: ErrorType
    message: str
    details: str = ""
    recoverable: bool = True  # 是否可恢复
    retry_after: int | None = None  # 多少秒后重试

    def to_tool_message_content(self) -> str:
        """转换为 ToolMessage 格式的内容。"""
        content = f"[{self.error_type.value.upper()}] {self.message}"
        if self.details:
            content += f"\n详情: {self.details}"
        if self.retry_after:
            content += f"\n请 {self.retry_after} 秒后重试"
        return content

    def to_human_message_content(self) -> str:
        """转换为 HumanMessage 格式的内容。"""
        return f"错误: {self.message}"


class ErrorHandlingMiddleware(BaseMiddleware):
    """错误处理中间件。

    功能：
    1. 捕获并分类错误
    2. 转换为友好的错误消息
    3. 根据错误类型决定是否可恢复
    4. 注入错误消息到状态中

    配置：
    - error_handling_enabled: 是否启用错误处理
    - max_retries: 最大重试次数
    - fallback_message: 降级时的默认消息
    """

    name: str = "error_handling"
    description: str = "统一处理 Agent 执行过程中的错误"

    # 默认错误消息
    DEFAULT_FALLBACK_MESSAGE = "处理请求时遇到问题，请稍后重试。"
    DEFAULT_MODEL_ERROR_MESSAGE = "暂时无法处理请求，请稍后重试。"
    DEFAULT_TOOL_ERROR_MESSAGE = "工具执行失败，请检查参数或稍后重试。"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 0,
        max_retries: int = 3,
        fallback_message: str | None = None,
        include_traceback: bool = False,
    ):
        """初始化错误处理中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            max_retries: 最大重试次数
            fallback_message: 降级消息
            include_traceback: 是否在日志中包含堆栈跟踪
        """
        super().__init__(enabled=enabled, order=order)
        self.max_retries = max_retries
        self.fallback_message = fallback_message or self.DEFAULT_FALLBACK_MESSAGE
        self.include_traceback = include_traceback

        # 重试计数器
        self._retry_counts: dict[str, int] = {}

    def _classify_error(self, error: Exception) -> ErrorInfo:
        """分类错误类型。

        Args:
            error: 异常对象

        Returns:
            ErrorInfo 实例
        """
        error_msg = str(error).lower()
        error_type = type(error).__name__

        # 模型相关错误
        if any(keyword in error_msg for keyword in ["rate limit", "rate_limit", "429", "too many requests"]):
            return ErrorInfo(
                error_type=ErrorType.MODEL_RATE_LIMIT,
                message="请求过于频繁，请稍后重试。",
                details=str(error),
                recoverable=True,
                retry_after=5,
            )

        if any(keyword in error_msg for keyword in ["timeout", "timed out", "504", "gateway timeout"]):
            return ErrorInfo(
                error_type=ErrorType.MODEL_TIMEOUT,
                message="请求超时，请稍后重试。",
                details=str(error),
                recoverable=True,
                retry_after=3,
            )

        if any(keyword in error_msg for keyword in ["openai", "anthropic", "dashscope", "model", "api"]):
            return ErrorInfo(
                error_type=ErrorType.MODEL_ERROR,
                message=self.DEFAULT_MODEL_ERROR_MESSAGE,
                details=str(error),
                recoverable=True,
            )

        # 工具相关错误
        if "tool" in error_msg or "not found" in error_msg or "not exist" in error_msg:
            if "argument" in error_msg or "parameter" in error_msg or "invalid" in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.TOOL_ARGUMENT_ERROR,
                    message="工具参数错误，请检查输入。",
                    details=str(error),
                    recoverable=False,
                )
            return ErrorInfo(
                error_type=ErrorType.TOOL_EXECUTION_ERROR,
                message=self.DEFAULT_TOOL_ERROR_MESSAGE,
                details=str(error),
                recoverable=True,
            )

        if "timeout" in error_msg:
            return ErrorInfo(
                error_type=ErrorType.TOOL_TIMEOUT,
                message="工具执行超时，请稍后重试。",
                details=str(error),
                recoverable=True,
                retry_after=5,
            )

        # 默认未知错误
        return ErrorInfo(
            error_type=ErrorType.UNKNOWN_ERROR,
            message=self.fallback_message,
            details=str(error),
            recoverable=True,
        )

    def _get_retry_count(self, thread_id: str) -> int:
        """获取当前线程的重试次数。"""
        return self._retry_counts.get(thread_id, 0)

    def _increment_retry_count(self, thread_id: str) -> int:
        """增加并返回重试次数。"""
        count = self._retry_counts.get(thread_id, 0) + 1
        self._retry_counts[thread_id] = count
        return count

    def _reset_retry_count(self, thread_id: str) -> None:
        """重置重试计数。"""
        self._retry_counts.pop(thread_id, None)

    async def wrap_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[..., Any],
        runtime: dict[str, Any],
    ) -> Any:
        """包装工具调用，捕获执行错误。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            handler: 实际执行函数
            runtime: 运行时上下文

        Returns:
            工具执行结果或错误 ToolMessage
        """
        thread_id = runtime.get("thread_id", "default")

        try:
            result = await handler()
            self._reset_retry_count(thread_id)
            return result

        except Exception as e:
            error_info = self._classify_error(e)

            logger.error(
                f"工具执行错误: tool={tool_name}, error={error_info.message}",
                exc_info=self.include_traceback,
            )

            # 检查是否可恢复
            retry_count = self._get_retry_count(thread_id)
            if error_info.recoverable and retry_count < self.max_retries:
                self._increment_retry_count(thread_id)
                logger.info(f"错误可恢复，重试次数: {retry_count + 1}/{self.max_retries}")

            # 返回错误 ToolMessage
            return ToolMessage(
                content=error_info.to_tool_message_content(),
                name=tool_name,
                tool_call_id=tool_args.get("id") or tool_args.get("tool_call_id", ""),
                status="error",
            )

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用后检查错误。

        检测状态中的错误字段，生成友好的错误消息。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        error = state.get("error")

        if not error:
            return None

        # 将错误转换为友好消息
        if isinstance(error, Exception):
            error_info = self._classify_error(error)
            error_message = error_info.to_human_message_content()
        else:
            error_message = str(error)

        # 记录错误日志
        logger.error(f"Agent 执行错误: {error_message}")

        # 可以选择注入错误消息到消息列表
        # 这会让 Agent 看到错误并尝试恢复
        return MiddlewareResult.with_messages([
            AIMessage(content=f"[系统] {error_message}")
        ])

    async def after_agent(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """Agent 执行后清理。"""
        thread_id = runtime.get("thread_id", "default")
        self._reset_retry_count(thread_id)
        return None


class ToolErrorWrapper:
    """工具错误包装器。

    可单独用于包装任何工具函数。

    示例：
    ```python
    @ToolErrorWrapper.wrap
    async def my_tool(arg1, arg2):
        # 工具逻辑
        pass
    ```
    """

    @staticmethod
    def wrap(
        func: Callable[..., Awaitable[Any]],
        error_message: str | None = None,
    ) -> Callable[..., Awaitable[Any]]:
        """装饰器包装工具函数。

        Args:
            func: 要包装的异步函数
            error_message: 错误消息模板

        Returns:
            包装后的函数
        """
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                msg = error_message or f"工具执行失败: {str(e)}"
                logger.error(msg, exc_info=True)
                return ToolMessage(
                    content=msg,
                    name=getattr(func, "__name__", "unknown"),
                    status="error",
                )

        return wrapper

    @staticmethod
    def sync_wrap(
        func: Callable[..., Any],
        error_message: str | None = None,
    ) -> Callable[..., Any]:
        """同步版本的装饰器包装。"""
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                msg = error_message or f"工具执行失败: {str(e)}"
                logger.error(msg, exc_info=True)
                return ToolMessage(
                    content=msg,
                    name=getattr(func, "__name__", "unknown"),
                    status="error",
                )

        return wrapper
