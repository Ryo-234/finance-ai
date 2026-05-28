"""中间件配置 - 集中管理所有中间件的配置参数。

该模块定义中间件相关的配置结构和默认值。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ErrorHandlingConfig:
    """错误处理中间件配置。"""

    enabled: bool = True
    order: int = 0
    max_retries: int = 3
    fallback_message: str | None = None
    include_traceback: bool = False


@dataclass
class LoopDetectionConfig:
    """循环检测中间件配置。"""

    enabled: bool = True
    order: int = 10
    warn_threshold: int = 3  # 软限制（警告）
    hard_limit: int = 5  # 硬限制（强制停止）
    window_size: int = 20  # 滑动窗口大小
    max_tracked_threads: int = 100  # 最大跟踪线程数
    tool_freq_warn: int = 30  # 工具频率警告阈值
    tool_freq_hard_limit: int = 50  # 工具频率硬限制


@dataclass
class MemoryConfig:
    """记忆中间件配置。"""

    enabled: bool = True
    order: int = 50
    min_messages: int = 2
    debounce_seconds: float = 30.0


@dataclass
class MemoryInjectionConfig:
    """记忆注入中间件配置。"""

    enabled: bool = True
    order: int = -10
    max_injection_tokens: int = 2000
    memory_key: str = "memory_context"


@dataclass
class TokenTrackingConfig:
    """Token 追踪中间件配置。"""

    enabled: bool = True
    order: int = 20
    context_limit: int = 128000
    warning_threshold: float = 0.8  # 80%
    critical_threshold: float = 0.95  # 95%
    track_per_thread: bool = True
    log_usage: bool = True


@dataclass
class SummarizationConfig:
    """上下文压缩中间件配置。"""

    enabled: bool = True
    order: int = -5
    token_limit: int = 6000  # 触发压缩的 token 阈值
    keep_messages: int = 10  # 压缩后保留的最近消息数


@dataclass
class ContextCompressionConfig:
    """简单上下文压缩中间件配置。"""

    enabled: bool = True
    order: int = -5
    max_messages: int = 20  # 最大保留消息数


@dataclass
class MiddlewareConfig:
    """中间件总配置。"""

    error_handling: ErrorHandlingConfig = field(default_factory=ErrorHandlingConfig)
    loop_detection: LoopDetectionConfig = field(default_factory=LoopDetectionConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    memory_injection: MemoryInjectionConfig = field(default_factory=MemoryInjectionConfig)
    token_tracking: TokenTrackingConfig = field(default_factory=TokenTrackingConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)
    context_compression: ContextCompressionConfig = field(default_factory=ContextCompressionConfig)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "MiddlewareConfig":
        """从字典创建配置。

        Args:
            config: 配置字典

        Returns:
            MiddlewareConfig 实例
        """
        return cls(
            error_handling=ErrorHandlingConfig(
                **config.get("error_handling", {})
            ),
            loop_detection=LoopDetectionConfig(
                **config.get("loop_detection", {})
            ),
            memory=MemoryConfig(
                **config.get("memory", {})
            ),
            memory_injection=MemoryInjectionConfig(
                **config.get("memory_injection", {})
            ),
            token_tracking=TokenTrackingConfig(
                **config.get("token_tracking", {})
            ),
            summarization=SummarizationConfig(
                **config.get("summarization", {})
            ),
            context_compression=ContextCompressionConfig(
                **config.get("context_compression", {})
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            配置字典
        """
        return {
            "error_handling": {
                "enabled": self.error_handling.enabled,
                "order": self.error_handling.order,
                "max_retries": self.error_handling.max_retries,
                "fallback_message": self.error_handling.fallback_message,
                "include_traceback": self.error_handling.include_traceback,
            },
            "loop_detection": {
                "enabled": self.loop_detection.enabled,
                "order": self.loop_detection.order,
                "warn_threshold": self.loop_detection.warn_threshold,
                "hard_limit": self.loop_detection.hard_limit,
                "window_size": self.loop_detection.window_size,
                "max_tracked_threads": self.loop_detection.max_tracked_threads,
                "tool_freq_warn": self.loop_detection.tool_freq_warn,
                "tool_freq_hard_limit": self.loop_detection.tool_freq_hard_limit,
            },
            "memory": {
                "enabled": self.memory.enabled,
                "order": self.memory.order,
                "min_messages": self.memory.min_messages,
                "debounce_seconds": self.memory.debounce_seconds,
            },
            "memory_injection": {
                "enabled": self.memory_injection.enabled,
                "order": self.memory_injection.order,
                "max_injection_tokens": self.memory_injection.max_injection_tokens,
                "memory_key": self.memory_injection.memory_key,
            },
            "token_tracking": {
                "enabled": self.token_tracking.enabled,
                "order": self.token_tracking.order,
                "context_limit": self.token_tracking.context_limit,
                "warning_threshold": self.token_tracking.warning_threshold,
                "critical_threshold": self.token_tracking.critical_threshold,
                "track_per_thread": self.token_tracking.track_per_thread,
                "log_usage": self.token_tracking.log_usage,
            },
            "summarization": {
                "enabled": self.summarization.enabled,
                "order": self.summarization.order,
                "token_limit": self.summarization.token_limit,
                "keep_messages": self.summarization.keep_messages,
            },
            "context_compression": {
                "enabled": self.context_compression.enabled,
                "order": self.context_compression.order,
                "max_messages": self.context_compression.max_messages,
            },
        }


# 默认配置实例
_default_config: MiddlewareConfig | None = None


def get_middleware_config() -> MiddlewareConfig:
    """获取中间件配置（全局单例）。"""
    global _default_config
    if _default_config is None:
        _default_config = MiddlewareConfig()
    return _default_config


def update_middleware_config(config: MiddlewareConfig) -> None:
    """更新中间件配置。"""
    global _default_config
    _default_config = config


def reset_middleware_config() -> None:
    """重置中间件配置为默认值。"""
    global _default_config
    _default_config = MiddlewareConfig()
