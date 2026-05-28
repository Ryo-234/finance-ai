"""中间件系统测试。"""

import asyncio
import pytest
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from middleware.base import BaseMiddleware, MiddlewareResult, HookType
from middleware.manager import MiddlewareManager, get_runtime_context, set_runtime_context
from middleware.factory import (
    MiddlewareFactory,
    create_default_manager,
    ErrorHandlingMiddleware,
    LoopDetectionMiddleware,
    MemoryMiddleware,
    TokenTrackingMiddleware,
)


class TestMiddlewareResult:
    """测试 MiddlewareResult 类。"""

    def test_none_result(self):
        """测试创建空结果。"""
        result = MiddlewareResult.none()
        assert result.updates == {}
        assert result.messages == []
        assert result.stop is False
        assert result.error is None

    def test_updated_result(self):
        """测试创建更新结果。"""
        result = MiddlewareResult.updated({"key": "value"})
        assert result.updates == {"key": "value"}
        assert result.messages == []

    def test_with_messages(self):
        """测试创建带消息的结果。"""
        msg = HumanMessage(content="test")
        result = MiddlewareResult.with_messages([msg])
        assert len(result.messages) == 1
        assert result.messages[0] == msg

    def test_stopped_result(self):
        """测试创建停止结果。"""
        result = MiddlewareResult.stopped("loop detected")
        assert result.stop is True
        assert result.error == "loop detected"

    def test_merge(self):
        """测试合并结果。"""
        msg1 = HumanMessage(content="msg1")
        msg2 = HumanMessage(content="msg2")

        result1 = MiddlewareResult(
            updates={"key1": "value1"},
            messages=[msg1],
        )

        result2 = MiddlewareResult(
            updates={"key2": "value2"},
            messages=[msg2],
        )

        merged = result1.merge(result2)
        assert merged.updates == {"key1": "value1", "key2": "value2"}
        assert len(merged.messages) == 2


class DummyMiddleware(BaseMiddleware):
    """测试用的虚拟中间件。"""

    def __init__(self, order: int = 0, enabled: bool = True, name: str = "dummy"):
        super().__init__(enabled=enabled, order=order)
        self.before_called = False
        self.after_called = False
        self.state_received = None
        self.mw_name = name

    @property
    def name(self) -> str:
        return self.mw_name

    async def before_model(
        self, state: dict[str, Any], runtime: dict[str, Any]
    ) -> MiddlewareResult | None:
        self.before_called = True
        self.state_received = state
        return MiddlewareResult.updated({"before_key": "before_value"})

    async def after_model(
        self, state: dict[str, Any], runtime: dict[str, Any]
    ) -> MiddlewareResult | None:
        self.after_called = True
        self.state_received = state
        return MiddlewareResult.updated({"after_key": "after_value"})


class TestMiddlewareManager:
    """测试 MiddlewareManager 类。"""

    def test_add_middleware(self):
        """测试添加中间件。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware()
        manager.add(mw, name="dummy")

        assert manager.enabled_count == 1
        assert manager.get("dummy") == mw

    def test_remove_middleware(self):
        """测试移除中间件。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware()
        manager.add(mw, name="dummy")

        assert manager.enabled_count == 1
        manager.remove("dummy")
        assert manager.enabled_count == 0

    def test_order_sorting(self):
        """测试中间件按 order 排序。"""
        manager = MiddlewareManager()

        mw1 = DummyMiddleware(order=10, name="mw1")
        mw2 = DummyMiddleware(order=0, name="mw2")
        mw3 = DummyMiddleware(order=5, name="mw3")

        manager.add(mw1, name="mw1")
        manager.add(mw2, name="mw2")
        manager.add(mw3, name="mw3")

        middlewares = manager.middlewares
        assert middlewares[0].name == "mw2"  # order=0
        assert middlewares[1].name == "mw3"  # order=5
        assert middlewares[2].name == "mw1"  # order=10

    def test_disabled_middleware_skipped(self):
        """测试禁用的中间件被跳过。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware(enabled=False)
        manager.add(mw, name="disabled")

        assert manager.enabled_count == 0

    def test_list_middlewares(self):
        """测试列出中间件信息。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware(order=5, name="test")
        mw.description = "测试中间件"
        manager.add(mw, name="test")

        info = manager.list_middlewares()
        assert len(info) == 1
        assert info[0]["name"] == "test"
        assert info[0]["order"] == 5


class TestMiddlewareIntegration:
    """测试中间件集成。"""

    @pytest.mark.asyncio
    async def test_before_model_middleware(self):
        """测试 before_model 中间件应用。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware()
        manager.add(mw, name="dummy")

        state = {"key": "value"}
        runtime = {"thread_id": "test"}

        result = await manager.apply_before_model(state, runtime)

        assert mw.before_called is True
        assert result.updates == {"before_key": "before_value"}

    @pytest.mark.asyncio
    async def test_after_model_middleware(self):
        """测试 after_model 中间件应用。"""
        manager = MiddlewareManager()
        mw = DummyMiddleware()
        manager.add(mw, name="dummy")

        state = {"key": "value"}
        runtime = {"thread_id": "test"}

        result = await manager.apply_after_model(state, runtime)

        assert mw.after_called is True
        assert result.updates == {"after_key": "after_value"}

    @pytest.mark.asyncio
    async def test_middleware_chain(self):
        """测试中间件链执行。"""
        manager = MiddlewareManager()

        results = []

        class TrackingMiddleware(BaseMiddleware):
            def __init__(self, name: str, order: int = 0):
                super().__init__(order=order)
                self.name = name

            async def before_model(self, state, runtime):
                results.append(f"{self.name}_before")
                return None

            async def after_model(self, state, runtime):
                results.append(f"{self.name}_after")
                return None

        mw1 = TrackingMiddleware("first", order=0)
        mw2 = TrackingMiddleware("second", order=1)
        manager.add(mw1, name="first")
        manager.add(mw2, name="second")

        state = {}
        runtime = {}

        await manager.apply_before_model(state, runtime)
        await manager.apply_after_model(state, runtime)

        assert results == ["first_before", "second_before", "first_after", "second_after"]


class TestLoopDetection:
    """测试循环检测中间件。"""

    @pytest.mark.asyncio
    async def test_no_loop_detection(self):
        """测试无循环时不触发检测。"""
        mw = LoopDetectionMiddleware(warn_threshold=3, hard_limit=5)

        messages = [
            HumanMessage(content="用户问题"),
            AIMessage(content="回答"),
        ]

        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.after_model(state, runtime)

        assert result is None

    @pytest.mark.asyncio
    async def test_loop_warning(self):
        """测试循环警告（连续2次相同调用）。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_limit=5)
        mw.reset("test")  # 重置状态

        tool_call = {"name": "search", "args": {"query": "test"}, "id": "call_1"}

        # 模拟连续2次模型调用，每次都返回相同的 tool_calls
        runtime = {"thread_id": "test"}

        for i in range(2):
            messages = [
                AIMessage(content="搜索结果", tool_calls=[tool_call.copy()])
            ]
            state = {"messages": messages}
            result = await mw.after_model(state, runtime)

        # 软限制触发（warn_threshold=2，第2次应该触发）
        assert result is not None
        assert len(result.messages) > 0 or result.stop is True

    @pytest.mark.asyncio
    async def test_loop_hard_stop(self):
        """测试循环硬停止（连续3次相同调用）。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_limit=3)
        mw.reset("test")  # 重置状态

        tool_call = {"name": "search", "args": {"query": "test"}, "id": "call_1"}

        # 模拟连续3次模型调用，每次都返回相同的 tool_calls
        runtime = {"thread_id": "test"}

        for i in range(3):
            messages = [
                AIMessage(content="搜索结果", tool_calls=[tool_call.copy()])
            ]
            state = {"messages": messages}
            result = await mw.after_model(state, runtime)

        # 硬限制触发（hard_limit=3，第3次应该触发）
        assert result is not None
        assert result.stop is True or "messages" in result.updates


class TestErrorHandling:
    """测试错误处理中间件。"""

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        """测试工具错误包装。"""
        mw = ErrorHandlingMiddleware()

        runtime = {"thread_id": "test"}

        async def failing_tool():
            raise ValueError("工具执行失败")

        result = await mw.wrap_tool_call(
            tool_name="test_tool",
            tool_args={"id": "call_123"},
            handler=failing_tool,
            runtime=runtime,
        )

        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "错误" in result.content or "失败" in result.content

    @pytest.mark.asyncio
    async def test_successful_tool_execution(self):
        """测试工具成功执行。"""
        mw = ErrorHandlingMiddleware()

        runtime = {"thread_id": "test"}

        async def successful_tool():
            return "success result"

        result = await mw.wrap_tool_call(
            tool_name="test_tool",
            tool_args={},
            handler=successful_tool,
            runtime=runtime,
        )

        assert result == "success result"


class TestTokenTracking:
    """测试 Token 追踪中间件。"""

    @pytest.mark.asyncio
    async def test_token_extraction(self):
        """测试 Token 使用量提取。"""
        mw = TokenTrackingMiddleware()

        # 模拟带 usage 的 AIMessage
        message = AIMessage(
            content="测试回答",
            response_metadata={
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                "model": "gpt-4",
            },
        )

        state = {"messages": [message]}
        runtime = {"thread_id": "test"}

        result = await mw.after_model(state, runtime)

        # 检查统计
        stats = mw.get_stats("test")
        assert stats["total_tokens"] == 150
        assert stats["request_count"] == 1

    @pytest.mark.asyncio
    async def test_token_warning(self):
        """测试 Token 警告。"""
        mw = TokenTrackingMiddleware(
            context_limit=100,  # 小限制方便测试
            warning_threshold=0.8,
        )

        # 模拟高 Token 使用
        message = AIMessage(
            content="x" * 1000,  # 模拟大回复
            response_metadata={
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 60,  # 超过 80% 的 100
                    "total_tokens": 110,
                },
                "model": "gpt-4",
            },
        )

        state = {"messages": [message]}
        runtime = {"thread_id": "test"}

        result = await mw.after_model(state, runtime)

        # 应该返回警告消息
        assert result is not None
        assert len(result.messages) > 0


class TestFactory:
    """测试中间件工厂。"""

    def test_create_default_manager(self):
        """测试创建默认管理器。"""
        manager = create_default_manager()

        assert manager.enabled_count > 0
        # 检查关键中间件
        assert manager.get("error_handling") is not None
        assert manager.get("loop_detection") is not None
        assert manager.get("memory") is not None

    def test_custom_config_factory(self):
        """测试自定义配置工厂。"""
        config = {
            "error_handling": {
                "enabled": True,
                "order": 0,
                "max_retries": 5,
            },
            "loop_detection": {
                "enabled": False,  # 禁用
            },
        }

        factory = MiddlewareFactory(config)
        manager = factory.create_manager()

        assert manager.enabled_count >= 1
        # error_handling 应该存在且配置正确
        error_mw = manager.get("error_handling")
        assert error_mw is not None
        assert error_mw.max_retries == 5


class TestRuntimeContext:
    """测试运行时上下文。"""

    def test_get_runtime_context(self):
        """测试获取运行时上下文。"""
        ctx = get_runtime_context()
        assert isinstance(ctx, dict)

    def test_set_and_get_runtime_context(self):
        """测试设置和获取运行时上下文。"""
        ctx = {"thread_id": "test", "user_id": "user1"}
        set_runtime_context(ctx)

        retrieved = get_runtime_context()
        assert retrieved["thread_id"] == "test"
        assert retrieved["user_id"] == "user1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
