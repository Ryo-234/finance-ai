"""记忆系统配置模块。"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class MemoryConfig:
    """记忆系统配置类。"""

    # 是否启用记忆系统
    enabled: bool = True
    # 是否启用记忆注入到提示词
    injection_enabled: bool = True
    # 存储路径（空=按用户隔离存储）
    storage_path: str = ""
    # 防抖延迟秒数
    debounce_seconds: float = 30.0
    # 用于记忆更新的模型名称（null=使用默认模型）
    model_name: Optional[str] = None
    # 最大事实数量
    max_facts: int = 100
    # 事实置信度阈值
    fact_confidence_threshold: float = 0.7
    # 最大注入 token 数
    max_injection_tokens: int = 2000


_config: Optional[MemoryConfig] = None


def get_memory_config() -> MemoryConfig:
    """获取记忆配置单例。"""
    global _config
    if _config is None:
        _config = MemoryConfig(
            enabled=True,
            injection_enabled=True,
            debounce_seconds=30.0,
            max_facts=100,
            fact_confidence_threshold=0.7,
            max_injection_tokens=2000,
        )
    return _config