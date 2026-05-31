"""中间件管理器 - 管理中间件链的执行。

参考 DeerFlow 的中间件链设计，提供标准化的中间件执行顺序管理。
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from collections import OrderedDict
import logging
import threading
from contextvars import ContextVar
from copy import deepcopy

from middleware.base import BaseMiddleware, HookType, MiddlewareResult

logger = logging.getLogger(__name__)

# 运行时上下文 ContextVar
_runtime_context: ContextVar[dict[str, Any]] = ContextVar("runtime_context", default={})


def get_runtime_context() -> dict[str, Any]:
    """获取当前运行时上下文。"""
    return _runtime_context.get()


def set_runtime_context(context: dict[str, Any]) -> None:
    """设置当前运行时上下文。"""
    _runtime_context.set(context)


class MiddlewareManager:
    """中间件链管理器。

    负责注册、排序和执行中间件。

    使用示例：
    ```python
    # 创建管理器
    manager = MiddlewareManager()

    # 注册中间件（按添加顺序排序，可通过 order 参数调整）
    manager.add(ErrorHandlingMiddleware())
    manager.add(LoopDetectionMiddleware(warn_threshold=3, hard_limit=5))
    manager.add(MemoryMiddleware(memory_queue))

    # 在模型调用前应用所有中间件
    async def call_model(state, model, runtime):
        # before_model 阶段
        before_result = await manager.apply_before_model(state, runtime)

        # 执行模型调用
        result = await model.ainvoke(...)

        # after_model 阶段
        after_result = await manager.apply_after_model(state, runtime)

        return merge_results(before_result, after_result)
    ```

    中间件执行顺序：
    1. 按 order 排序（从小到大）
    2. order 相同时按注册顺序
    3. enabled=False 的中间件会被跳过
    """

    def __init__(self):
        """初始化中间件管理器。"""
        self._middlewares: OrderedDict[str, BaseMiddleware] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, middleware: BaseMiddleware, name: str | None = None) -> "MiddlewareManager":
        """注册中间件。

        Args:
            middleware: 中间件实例
            name: 中间件名称（默认使用类名）

        Returns:
            返回 self，支持链式调用
        """
        with self._lock:
            key = name or middleware.__class__.__name__
            if key in self._middlewares:
                logger.warning(f"中间件 '{key}' 已存在，将被替换")
            self._middlewares[key] = middleware
            # 按 order 重新排序
            self._sort_middlewares()
            logger.debug(f"添加中间件: {key} (order={middleware.order})")
        return self

    def remove(self, name: str) -> bool:
        """移除中间件。

        Args:
            name: 中间件名称

        Returns:
            是否成功移除
        """
        with self._lock:
            if name in self._middlewares:
                del self._middlewares[name]
                logger.debug(f"移除中间件: {name}")
                return True
            return False

    def get(self, name: str) -> BaseMiddleware | None:
        """获取中间件。"""
        return self._middlewares.get(name)

    def clear(self) -> None:
        """清除所有中间件。"""
        with self._lock:
            self._middlewares.clear()
            logger.debug("已清除所有中间件")

    def _sort_middlewares(self) -> None:
        """按 order 排序中间件。"""
        self._middlewares = OrderedDict(
            sorted(self._middlewares.items(), key=lambda x: x[1].order)
        )

    @property
    def middlewares(self) -> list[BaseMiddleware]:
        """获取所有已注册的中间件列表（按执行顺序）。"""
        with self._lock:
            return [m for m in self._middlewares.values() if m.enabled]

    @property
    def enabled_count(self) -> int:
        """获取已启用的中间件数量。"""
        return len(self.middlewares)

    def list_middlewares(self) -> list[dict[str, Any]]:
        """列出所有中间件信息。"""
        with self._lock:
            return [
                {
                    "name": name,
                    "class": mw.__class__.__name__,
                    "enabled": mw.enabled,
                    "order": mw.order,
                    "description": mw.description,
                }
                for name, mw in self._middlewares.items()
            ]

    async def apply_before_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult:
        """应用所有 before_model 钩子。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            合并后的 MiddlewareResult
        """
        runtime = runtime or get_runtime_context()
        result = MiddlewareResult.none()

        for middleware in self.middlewares:
            try:
                middleware_result = await middleware.before_model(state, runtime)
                if middleware_result is not None:
                    if isinstance(middleware_result, MiddlewareResult):
                        result = result.merge(middleware_result)
                    else:
                        # 如果返回的是 dict，当作 updates 处理
                        result = result.merge(MiddlewareResult(updates=middleware_result))
            except Exception as e:
                logger.exception(f"中间件 {middleware.name} before_model 执行失败: {e}")
                result = result.merge(
                    MiddlewareResult(error=f"{middleware.name}: {str(e)}")
                )

            # 如果中间件要求停止，跳出循环
            if result.stop:
                logger.info(f"中间件 {middleware.name} 要求停止处理")
                break

        return result

    async def apply_after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult:
        """应用所有 after_model 钩子。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            合并后的 MiddlewareResult
        """
        runtime = runtime or get_runtime_context()
        result = MiddlewareResult.none()

        for middleware in self.middlewares:
            try:
                middleware_result = await middleware.after_model(state, runtime)
                if middleware_result is not None:
                    if isinstance(middleware_result, MiddlewareResult):
                        result = result.merge(middleware_result)
                    else:
                        result = result.merge(MiddlewareResult(updates=middleware_result))
            except Exception as e:
                logger.exception(f"中间件 {middleware.name} after_model 执行失败: {e}")
                result = result.merge(
                    MiddlewareResult(error=f"{middleware.name}: {str(e)}")
                )

            if result.stop:
                logger.info(f"中间件 {middleware.name} 要求停止处理")
                break

        return result

    async def apply_after_agent(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult:
        """应用所有 after_agent 钩子。

        用于异步任务（如记忆更新）。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            合并后的 MiddlewareResult
        """
        runtime = runtime or get_runtime_context()
        result = MiddlewareResult.none()

        for middleware in self.middlewares:
            try:
                middleware_result = await middleware.after_agent(state, runtime)
                if middleware_result is not None:
                    if isinstance(middleware_result, MiddlewareResult):
                        result = result.merge(middleware_result)
                    else:
                        result = result.merge(MiddlewareResult(updates=middleware_result))
            except Exception as e:
                logger.exception(f"中间件 {middleware.name} after_agent 执行失败: {e}")

        return result

    async def apply_before_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult:
        """应用所有 before_tool 钩子。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            runtime: 运行时上下文

        Returns:
            合并后的 MiddlewareResult
        """
        runtime = runtime or get_runtime_context()
        result = MiddlewareResult.none()

        for middleware in self.middlewares:
            try:
                middleware_result = await middleware.before_tool(
                    tool_name, tool_args, runtime
                )
                if middleware_result is not None:
                    if isinstance(middleware_result, MiddlewareResult):
                        result = result.merge(middleware_result)
                    else:
                        result = result.merge(MiddlewareResult(updates=middleware_result))
            except Exception as e:
                logger.exception(f"中间件 {middleware.name} before_tool 执行失败: {e}")

        return result

    async def apply_after_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        runtime: dict[str, Any] | None = None,
    ) -> MiddlewareResult:
        """应用所有 after_tool 钩子。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            tool_result: 工具执行结果
            runtime: 运行时上下文

        Returns:
            合并后的 MiddlewareResult
        """
        runtime = runtime or get_runtime_context()
        result = MiddlewareResult.none()

        for middleware in self.middlewares:
            try:
                middleware_result = await middleware.after_tool(
                    tool_name, tool_args, tool_result, runtime
                )
                if middleware_result is not None:
                    if isinstance(middleware_result, MiddlewareResult):
                        result = result.merge(middleware_result)
                    else:
                        result = result.merge(MiddlewareResult(updates=middleware_result))
            except Exception as e:
                logger.exception(f"中间件 {middleware.name} after_tool 执行失败: {e}")

        return result

    async def wrap_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[..., Any],
        runtime: dict[str, Any] | None = None,
    ) -> Any:
        """包装工具调用。

        依次让每个中间件包装工具调用。

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            handler: 实际执行工具的函数
            runtime: 运行时上下文

        Returns:
            包装后的工具执行结果
        """
        runtime = runtime or get_runtime_context()

        # 构建包装链
        current_handler = handler

        for middleware in reversed(self.middlewares):
            middleware_ref = middleware

            async def wrapped_handler(
                mw=middleware_ref,
                h=current_handler,
            ) -> Any:
                return await mw.wrap_tool_call(tool_name, tool_args, h, runtime)

            current_handler = wrapped_handler

        return await current_handler()


class AgentExecutor:
    """集成中间件链的 Agent 执行器。

    提供标准化的 Agent 执行流程，集成中间件管理。

    使用示例：
    ```python
    executor = AgentExecutor(
        agent=my_agent,
        middleware_manager=manager,
    )

    result = await executor.execute(state)
    ```
    """

    def __init__(
        self,
        agent: Any,
        middleware_manager: MiddlewareManager | None = None,
    ):
        """初始化 Agent 执行器。

        Args:
            agent: 要执行的 Agent
            middleware_manager: 中间件管理器（可选）
        """
        self.agent = agent
        self.middleware_manager = middleware_manager or MiddlewareManager()

    async def execute(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 Agent（集成中间件）。

        执行流程：
        1. apply_before_model
        2. Agent.ainvoke
        3. apply_after_model
        4. apply_after_agent

        Args:
            state: 初始状态
            runtime: 运行时上下文

        Returns:
            最终状态
        """
        runtime = runtime or {}
        set_runtime_context(runtime)

        # 深拷贝状态，避免修改原始状态
        current_state = deepcopy(state)

        # Before Model 阶段
        before_result = await self.middleware_manager.apply_before_model(
            current_state, runtime
        )
        if before_result.updates:
            current_state = {**current_state, **before_result.updates}
        if before_result.messages:
            current_state["messages"] = current_state.get("messages", []) + before_result.messages
        if before_result.stop:
            logger.info("before_model 阶段要求停止")
            return current_state

        # Agent 执行
        try:
            agent_result = await self.agent.ainvoke(current_state)
            current_state = {**current_state, **agent_result}
        except Exception as e:
            logger.exception(f"Agent 执行失败: {e}")
            current_state["error"] = str(e)

        # After Model 阶段
        after_result = await self.middleware_manager.apply_after_model(
            current_state, runtime
        )
        if after_result.updates:
            current_state = {**current_state, **after_result.updates}
        if after_result.messages:
            current_state["messages"] = current_state.get("messages", []) + after_result.messages

        # After Agent 阶段（异步任务）
        await self.middleware_manager.apply_after_agent(current_state, runtime)

        return current_state

    async def execute_node(
        self,
        node_name: str,
        node_handler: Callable[..., Any],
        state: dict[str, Any],
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行单个图节点（集成中间件）。

        适用于 LangGraph 节点执行。

        Args:
            node_name: 节点名称
            node_handler: 节点处理函数
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            更新后的状态
        """
        runtime = runtime or {}
        set_runtime_context(runtime)

        current_state = deepcopy(state)

        # 工具执行包装
        async def wrapped_handler() -> Any:
            # Before Tool
            before_tool_result = await self.middleware_manager.apply_before_tool(
                node_name, current_state, runtime
            )
            if before_tool_result.updates:
                current_state = {**current_state, **before_tool_result.updates}

            # 执行节点
            try:
                result = await node_handler(current_state)
                current_state = {**current_state, **result}
            except Exception as e:
                logger.exception(f"节点 {node_name} 执行失败: {e}")
                current_state["error"] = str(e)
                return current_state

            # After Tool
            after_tool_result = await self.middleware_manager.apply_after_tool(
                node_name, current_state, result, runtime
            )
            if after_tool_result.updates:
                current_state = {**current_state, **after_tool_result.updates}

            return current_state

        # 使用中间件包装工具调用
        return await self.middleware_manager.wrap_tool_call(
            node_name, current_state, wrapped_handler, runtime
        )
