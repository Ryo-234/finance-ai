"""中间件基类定义。

提供标准化的中间件接口，参考 LangChain AgentMiddleware 协议设计。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar, Optional
from typing_extensions import ParamSpec
import logging

logger = logging.getLogger(__name__)

# 类型变量
P = ParamSpec("P")
T = TypeVar("T")


class HookType(Enum):
    """中间件钩子类型枚举。"""

    # 模型调用前（在 LLM 调用之前执行）
    BEFORE_MODEL = "before_model"

    # 模型调用后（在 LLM 调用之后执行）
    AFTER_MODEL = "after_model"

    # Agent 执行后（整个 Agent 执行完成后）
    AFTER_AGENT = "after_agent"

    # 工具调用前（工具执行前拦截）
    BEFORE_TOOL = "before_tool"

    # 工具调用后（工具执行后拦截）
    AFTER_TOOL = "after_tool"

    # 工具调用包装（包裹工具执行，可修改参数或结果）
    WRAP_TOOL_CALL = "wrap_tool_call"


@dataclass
class MiddlewareHook:
    """中间件钩子定义。

    包含钩子的类型和回调函数。
    """

    hook_type: HookType
    callback: Callable[..., Any]
    order: int = 0  # 执行顺序，数字越小越先执行


@dataclass
class MiddlewareResult:
    """中间件执行结果。

    中间件可以返回 None（不修改状态）或一个 dict（要合并到状态的更新）。
    """

    updates: dict[str, Any] = field(default_factory=dict)
    messages: list[Any] = field(default_factory=list)
    stop: bool = False  # 是否停止后续处理
    error: Optional[str] = None

    @classmethod
    def none(cls) -> "MiddlewareResult":
        """返回一个空的 MiddlewareResult。"""
        return cls()

    @classmethod
    def updated(cls, updates: dict[str, Any]) -> "MiddlewareResult":
        """返回一个包含状态更新的结果。"""
        return cls(updates=updates)

    @classmethod
    def with_messages(cls, messages: list[Any]) -> "MiddlewareResult":
        """返回一个包含消息注入的结果。"""
        return cls(messages=messages)

    @classmethod
    def stopped(cls, reason: str = "") -> "MiddlewareResult":
        """返回一个表示停止处理的结果。"""
        return cls(stop=True, error=reason)

    def merge(self, other: "MiddlewareResult") -> "MiddlewareResult":
        """合并两个结果。"""
        return MiddlewareResult(
            updates={**self.updates, **other.updates},
            messages=self.messages + other.messages,
            stop=self.stop or other.stop,
            error=other.error or self.error,
        )


class BaseMiddleware(ABC):
    """所有中间件的基类。

    参考 LangChain AgentMiddleware 协议设计，提供标准化的中间件接口。

    子类可以重写以下方法：
    - before_model: 在模型调用前执行
    - after_model: 在模型调用后执行
    - after_agent: 在 Agent 执行完成后执行
    - wrap_tool_call: 包装工具调用

    方法默认返回 None，表示不修改状态。
    如果返回 MiddlewareResult，则会合并到状态中。

    示例：
    ```python
    class MyMiddleware(BaseMiddleware):
        async def before_model(self, state: dict, runtime: dict) -> MiddlewareResult:
            # 在模型调用前注入消息
            return MiddlewareResult.with_messages([
                HumanMessage(content="System reminder: ...")
            ])

        async def after_model(self, state: dict, runtime: dict) -> MiddlewareResult:
            # 在模型调用后检查输出
            if self._detect_loop(state):
                return MiddlewareResult.stopped("Loop detected")
            return MiddlewareResult.none()
    ```
    """

    # 中间件名称
    name: str = "base_middleware"

    # 中间件描述
    description: str = "基础中间件"

    def __init__(self, enabled: bool = True, order: int = 0):
        """初始化中间件。

        Args:
            enabled: 是否启用该中间件
            order: 执行顺序，数字越小越先执行
        """
        self.enabled = enabled
        self.order = order

    async def before_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用前执行。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文（包含 thread_id, run_id 等）

        Returns:
            MiddlewareResult 或 None（不修改状态）
        """
        return None

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用后执行。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        return None

    async def after_agent(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在 Agent 执行完成后执行。

        用于异步任务（如记忆更新）。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        return None

    async def before_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在工具调用前执行。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        return None

    async def after_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在工具调用后执行。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            tool_result: 工具执行结果
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        return None

    async def wrap_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[..., Any],
        runtime: dict[str, Any],
    ) -> Any:
        """包装工具调用。

        可用于错误处理、日志记录等。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            handler: 实际执行工具的函数
            runtime: 运行时上下文

        Returns:
            工具执行结果
        """
        return await handler()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(enabled={self.enabled}, order={self.order})"

    def __str__(self) -> str:
        return self.__repr__()
