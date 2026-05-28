"""中间件系统 - 为 Agent 提供灵活的钩子机制。

该模块参考 DeerFlow 的 AgentMiddleware 设计，提供类似 LangChain AgentMiddleware 协议的中间件实现。

核心组件：
- BaseMiddleware: 所有中间件的基类
- MiddlewareManager: 中间件链管理器
- 核心中间件:
    - ErrorHandlingMiddleware: 工具/模型错误处理
    - LoopDetectionMiddleware: 循环调用检测
    - MemoryMiddleware: 记忆系统集成
    - MemoryInjectionMiddleware: 记忆上下文注入
    - TokenTrackingMiddleware: Token 使用追踪
    - SummarizationMiddleware: 上下文压缩（当接近 token 限制时）
    - ContextCompressionMiddleware: 简单上下文压缩（保留最近 N 条消息）

使用示例：
```python
from middleware import MiddlewareManager, ErrorHandlingMiddleware, LoopDetectionMiddleware

# 创建中间件管理器
manager = MiddlewareManager()

# 添加中间件
manager.add(ErrorHandlingMiddleware())
manager.add(LoopDetectionMiddleware())

# 在 Agent 执行前后调用
before_result = await manager.apply_before_model(state, runtime)
model_result = await model.ainvoke(...)
after_result = await manager.apply_after_model(state, runtime)
```
"""

from middleware.base import BaseMiddleware, MiddlewareHook, MiddlewareResult
from middleware.manager import MiddlewareManager, AgentExecutor
from middleware.error_handling import ErrorHandlingMiddleware, ToolErrorWrapper
from middleware.loop_detection import LoopDetectionMiddleware
from middleware.memory import MemoryMiddleware, MemoryInjectionMiddleware
from middleware.token_tracking import TokenTrackingMiddleware, TokenBudgetMiddleware
from middleware.summarization import SummarizationMiddleware, ContextCompressionMiddleware
from middleware.clarification import ClarificationMiddleware

__all__ = [
    # 基础组件
    "BaseMiddleware",
    "MiddlewareHook",
    "MiddlewareResult",
    "MiddlewareManager",
    "AgentExecutor",
    # 错误处理
    "ErrorHandlingMiddleware",
    "ToolErrorWrapper",
    # 循环检测
    "LoopDetectionMiddleware",
    # 记忆
    "MemoryMiddleware",
    "MemoryInjectionMiddleware",
    # Token 追踪
    "TokenTrackingMiddleware",
    "TokenBudgetMiddleware",
    # 上下文压缩
    "SummarizationMiddleware",
    "ContextCompressionMiddleware",
    # 澄清
    "ClarificationMiddleware",
]

