"""模型配置模块。"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """模型配置类。"""

    # 模型提供商：qwen / minimax
    provider: str = "qwen"
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


def _load_yaml_models() -> dict:
    """从 config.yaml 读取 models 配置段。"""
    from pathlib import Path
    import yaml

    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("models", {})
        except Exception:
            pass
    return {}


def get_model_config() -> ModelConfig:
    """获取模型配置单例。

    优先级：环境变量 > config.yaml > 硬编码默认值
    """
    global _config
    if _config is None:
        yaml_cfg = _load_yaml_models()
        provider = os.getenv("MODEL_PROVIDER") or yaml_cfg.get("default", "qwen")

        # 从 yaml 读取通用参数
        temperature = float(os.getenv("MODEL_TEMPERATURE") or yaml_cfg.get("temperature", 0.7))
        max_tokens = int(os.getenv("MODEL_MAX_TOKENS") or yaml_cfg.get("max_tokens", 4096))

        if provider == "minimax":
            _config = ModelConfig(
                provider="minimax",
                api_key=os.getenv("MINIMAX_API_KEY"),
                default_model=os.getenv("MINIMAX_DEFAULT_MODEL") or "MiniMax-M2.7-highspeed",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            _config = ModelConfig(
                provider="qwen",
                api_key=os.getenv("DASHSCOPE_API_KEY"),
                api_base=os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                default_model=os.getenv("DASHSCOPE_DEFAULT_MODEL") or "qwen-plus",
                temperature=temperature,
                max_tokens=max_tokens,
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
    config = get_model_config()

    if config.provider == "minimax":
        from config.minimax_chat import create_minimax_chat_model
        return create_minimax_chat_model(
            model_name=model_name or config.default_model,
            temperature=temperature or config.temperature,
            max_tokens=config.max_tokens,
        )
    else:
        from config.qwen_chat import create_qwen_chat_model
        return create_qwen_chat_model(
            model_name=model_name or config.default_model,
            temperature=temperature or config.temperature,
            max_tokens=config.max_tokens,
        )