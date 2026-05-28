"""模型配置模块。"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """模型配置类。"""

    # 默认模型名称
    default_model: str = "qwen-plus"
    # 温度参数
    temperature: float = 0.7
    # 最大 token 数
    max_tokens: int = 4096
    # 是否启用思考模式
    thinking_enabled: bool = False
    # API 基础 URL（用于代理或自定义端点）
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # API Key
    api_key: Optional[str] = None


_config: Optional[ModelConfig] = None


def get_model_config() -> ModelConfig:
    """获取模型配置单例。"""
    global _config
    if _config is None:
        _config = ModelConfig(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            api_base=os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
    return _config


def create_chat_model(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    thinking_enabled: bool = False,
):
    """创建聊天模型实例。

    参数：
        model_name: 模型名称，默认使用配置中的 default_model
        temperature: 温度参数，默认使用配置中的 temperature
        thinking_enabled: 是否启用思考模式

    返回：
        配置好的聊天模型实例
    """
    from config.qwen_chat import create_qwen_chat_model

    return create_qwen_chat_model(model_name=model_name, temperature=temperature)