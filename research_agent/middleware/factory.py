"""中间件工厂 - 根据配置创建中间件实例。

提供标准化的中间件创建接口，支持配置驱动。
"""

import logging
from typing import Any, Optional

from middleware import (
    BaseMiddleware,
    MiddlewareManager,
    ErrorHandlingMiddleware,
    LoopDetectionMiddleware,
    MemoryMiddleware,
    MemoryInjectionMiddleware,
    TokenTrackingMiddleware,
    SummarizationMiddleware,
    ContextCompressionMiddleware,
    ClarificationMiddleware,
)
from middleware.view_image import ViewImageMiddleware
from middleware.title_middleware import TitleMiddleware

logger = logging.getLogger(__name__)


class MiddlewareFactory:
    """中间件工厂类。

    根据配置创建和配置中间件实例。

    使用示例：
    ```python
    factory = MiddlewareFactory(config)

    # 创建所有启用的中间件
    manager = factory.create_manager()

    # 创建特定中间件
    loop_detection = factory.create_middleware("loop_detection")
    ```
    """

    # 中间件注册表
    MIDDLEWARE_CLASSES = {
        "error_handling": ErrorHandlingMiddleware,
        "loop_detection": LoopDetectionMiddleware,
        "memory": MemoryMiddleware,
        "memory_injection": MemoryInjectionMiddleware,
        "token_tracking": TokenTrackingMiddleware,
        "summarization": SummarizationMiddleware,
        "context_compression": ContextCompressionMiddleware,
        "clarification": ClarificationMiddleware,
        "view_image": ViewImageMiddleware,
        "title": TitleMiddleware,
    }

    def __init__(self, config: dict[str, Any] | None = None):
        """初始化工厂。

        Args:
            config: 中间件配置字典
        """
        self.config = config or {}

    def get_middleware_config(self, name: str) -> dict[str, Any]:
        """获取特定中间件的配置。

        Args:
            name: 中间件名称

        Returns:
            配置字典
        """
        return self.config.get(name, {})

    def is_middleware_enabled(self, name: str) -> bool:
        """检查中间件是否启用。

        Args:
            name: 中间件名称

        Returns:
            是否启用
        """
        middleware_config = self.get_middleware_config(name)
        # 默认为启用
        return middleware_config.get("enabled", True)

    def create_middleware(self, name: str) -> Optional[BaseMiddleware]:
        """创建单个中间件实例。

        Args:
            name: 中间件名称

        Returns:
            中间件实例或 None（如果未启用或不存在）
        """
        if not self.is_middleware_enabled(name):
            logger.debug(f"中间件 {name} 已禁用")
            return None

        middleware_class = self.MIDDLEWARE_CLASSES.get(name)
        if not middleware_class:
            logger.warning(f"未知的中间件类型: {name}")
            return None

        try:
            middleware_config = self.get_middleware_config(name)
            instance = middleware_class(**middleware_config)
            logger.info(f"创建中间件实例: {name}")
            return instance
        except Exception as e:
            logger.exception(f"创建中间件 {name} 失败: {e}")
            return None

    def create_manager(self) -> MiddlewareManager:
        """创建配置好的中间件管理器。

        Returns:
            MiddlewareManager 实例
        """
        manager = MiddlewareManager()

        # 按优先级顺序创建中间件
        middleware_order = [
            "error_handling",
            "clarification",  # 早期拦截澄清请求
            "token_tracking",
            "summarization",
            "context_compression",
            "memory",
            "memory_injection",
            "view_image",  # 在 memory_injection 之后执行
            "loop_detection",
            "title",  # 对话完成后生成标题
        ]

        for name in middleware_order:
            middleware = self.create_middleware(name)
            if middleware:
                manager.add(middleware, name=name)

        logger.info(f"中间件管理器已创建，启用 {manager.enabled_count} 个中间件")
        return manager


def _create_llm_summarizer():
    """创建 LLM 驱动的摘要生成器。

    返回一个 callable，接收消息列表，调用 LLM 生成简洁摘要。
    替代 SummarizationMiddleware 默认的纯文本拼接。
    """
    from config.models import create_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    model = create_chat_model()

    async def summarize(messages: list) -> str:
        """调用 LLM 生成对话摘要。

        参数：
            messages: 待压缩的消息列表

        返回：
            摘要文本
        """
        # 格式化消息内容
        parts = []
        for msg in messages:
            role = "用户" if isinstance(msg, HumanMessage) else (
                "助手" if isinstance(msg, AIMessage) else "系统"
            )
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            if content:
                parts.append(f"{role}: {content[:300]}")

        if not parts:
            return "（无对话内容）"

        conversation = "\n\n".join(parts[-20:])  # 最多取最近 20 条

        prompt = f"""请用 2-3 句话总结以下对话的关键信息和重要结论。只输出摘要文本，不要加任何前缀。

对话记录：
{conversation}

摘要："""

        try:
            response = await model.ainvoke([
                HumanMessage(content=prompt),
            ])
            return response.content.strip()
        except Exception as e:
            # LLM 调用失败时回退到简单拼接
            return "\n".join(
                f"[{getattr(m, 'type', 'msg')}] {str(getattr(m, 'content', ''))[:200]}"
                for m in messages[-8:]
            )

    # 导出同步包装（中间件调用时使用 await）
    return summarize


def create_default_manager() -> MiddlewareManager:
    """创建默认配置的中间件管理器。

    Returns:
        配置好的 MiddlewareManager
    """
    config = {
        "error_handling": {
            "enabled": True,
            "order": 0,
            "max_retries": 3,
        },
        "loop_detection": {
            "enabled": True,
            "order": 10,
            "warn_threshold": 3,
            "hard_limit": 5,
        },
        "memory": {
            "enabled": True,
            "order": 50,
        },
        "memory_injection": {
            "enabled": True,
            "order": -10,
        },
        "token_tracking": {
            "enabled": True,
            "order": 20,
            "log_usage": True,
        },
        "summarization": {
            "enabled": True,
            "order": -5,
            "token_limit": 6000,
            "keep_messages": 10,
            "summary_provider": _create_llm_summarizer(),  # 用 LLM 生成摘要而非纯文本截断
        },
        "context_compression": {
            "enabled": False,
            "order": -5,
            "max_messages": 20,
        },
        "clarification": {
            "enabled": True,
            "order": -100,  # 很早就执行，优先拦截
        },
        "view_image": {
            "enabled": True,
            "order": -8,  # 在 memory_injection 之后执行
        },
        "title": {
            "enabled": True,
            "order": 30,  # after_model 阶段，在插件链尾部
            "max_chars": 30,
        },
    }

    factory = MiddlewareFactory(config)
    return factory.create_manager()


# 全局默认管理器
_default_manager: Optional[MiddlewareManager] = None


def get_default_middleware_manager() -> MiddlewareManager:
    """获取默认的中间件管理器。

    Returns:
        MiddlewareManager 单例
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = create_default_manager()
    return _default_manager


def reset_default_manager() -> None:
    """重置默认中间件管理器。"""
    global _default_manager
    _default_manager = None
