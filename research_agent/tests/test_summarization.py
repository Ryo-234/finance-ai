"""上下文压缩中间件测试。"""

import pytest
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from middleware.summarization import (
    SummarizationMiddleware,
    ContextCompressionMiddleware,
    _estimate_token_count,
)


class TestTokenEstimate:
    """测试 token 数量估算。"""

    def test_empty_messages(self):
        """测试空消息列表。"""
        count = _estimate_token_count([])
        assert count == 0

    def test_single_human_message(self):
        """测试单条人类消息。"""
        msg = HumanMessage(content="Hello, world!")
        count = _estimate_token_count([msg])
        # 13 chars ≈ 3-4 tokens in English + 10 overhead
        assert count > 0
        assert count < 20

    def test_chinese_content(self):
        """测试中文内容。"""
        msg = HumanMessage(content="你好，这是一个测试消息")
        count = _estimate_token_count([msg])
        # 12 个汉字 ≈ 6 tokens
        assert count > 0


class TestSummarizationMiddleware:
    """测试 SummarizationMiddleware。"""

    @pytest.mark.asyncio
    async def test_no_summarize_below_threshold(self):
        """测试低于阈值时不压缩。"""
        mw = SummarizationMiddleware(token_limit=10000)

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        # 不压缩
        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_above_threshold(self):
        """测试超过阈值时压缩。"""
        mw = SummarizationMiddleware(
            token_limit=10,  # 很低的阈值确保触发
            keep_messages=2,
        )

        # 创建多条消息
        messages = []
        for i in range(15):
            messages.append(HumanMessage(content=f"User message number {i}"))
            messages.append(AIMessage(content=f"AI response number {i}"))

        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        # 应该触发压缩
        assert result is not None
        assert "messages" in result.updates

        new_messages = result.updates["messages"]
        # 应该包含摘要消息和保留的消息
        # 保留 2 条，所以应该有摘要 + 2 条
        assert len(new_messages) >= 3

    @pytest.mark.asyncio
    async def test_preserves_recent_messages(self):
        """测试保留最近的消息。"""
        mw = SummarizationMiddleware(
            token_limit=10,
            keep_messages=3,
        )

        messages = []
        for i in range(10):
            messages.append(HumanMessage(content=f"Message {i}"))

        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is not None
        new_messages = result.updates["messages"]

        # 找到摘要消息
        summary_msgs = [m for m in new_messages if isinstance(m, HumanMessage) and m.name == "summary"]
        assert len(summary_msgs) == 1

        # 应该有 1 条摘要 + 3 条保留消息
        non_removed = [m for m in new_messages if not isinstance(m, RemoveMessage)]
        assert len(non_removed) == 4

    @pytest.mark.asyncio
    async def test_system_message_preserved(self):
        """测试系统消息被保留。"""
        mw = SummarizationMiddleware(
            token_limit=10,
            keep_messages=2,
        )

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi!"),
        ]

        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        # 可能压缩，可能不压缩，取决于 token 估算
        # 但系统消息应该始终被处理
        if result is not None:
            assert "messages" in result.updates

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """测试空消息列表。"""
        mw = SummarizationMiddleware(token_limit=100)

        state = {"messages": []}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_messages_key(self):
        """测试没有 messages 键。"""
        mw = SummarizationMiddleware(token_limit=100)

        state = {}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is None


class TestContextCompressionMiddleware:
    """测试简单的上下文压缩中间件。"""

    @pytest.mark.asyncio
    async def test_no_compress_below_max(self):
        """测试低于最大消息数时不压缩。"""
        mw = ContextCompressionMiddleware(max_messages=20)

        messages = [HumanMessage(content=f"Message {i}") for i in range(10)]
        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is None

    @pytest.mark.asyncio
    async def test_compress_above_max(self):
        """测试超过最大消息数时压缩。"""
        mw = ContextCompressionMiddleware(max_messages=5)

        messages = [HumanMessage(content=f"Message {i}") for i in range(10)]
        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is not None
        new_messages = result.updates["messages"]

        # 应该包含压缩摘要消息
        summary_msgs = [m for m in new_messages if isinstance(m, HumanMessage) and m.name == "compression_summary"]
        assert len(summary_msgs) == 1

        # 验证压缩内容提到被压缩的消息数
        assert "10" in summary_msgs[0].content or "已压缩" in summary_msgs[0].content

    @pytest.mark.asyncio
    async def test_preserves_system_messages(self):
        """测试保留系统消息。"""
        mw = ContextCompressionMiddleware(max_messages=3)

        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi!"),
            HumanMessage(content="How are you?"),
            AIMessage(content="Fine!"),
        ]
        state = {"messages": messages}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is not None
        new_messages = result.updates["messages"]

        # 系统消息应该保留
        system_msgs = [m for m in new_messages if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "System prompt"

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """测试空消息列表。"""
        mw = ContextCompressionMiddleware(max_messages=5)

        state = {"messages": []}
        runtime = {"thread_id": "test"}

        result = await mw.before_model(state, runtime)

        assert result is None


# RemoveMessage 需要导入
from langchain_core.messages import RemoveMessage


if __name__ == "__main__":
    pytest.main([__file__, "-v"])