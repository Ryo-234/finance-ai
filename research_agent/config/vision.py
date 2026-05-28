"""视觉模型配置 - 统一接口。"""

import os
from typing import Optional


def create_vision_model():
    """创建视觉模型实例。

    根据配置选择：
    - qwen-vl: 使用 Qwen VL 模型（DashScope）
    - minimax-vl: 使用 MiniMax VL 模型（如果支持）

    Returns:
        视觉模型实例
    """
    # 优先使用 Qwen VL（DashScope 视觉模型）
    from config.qwen_vision import create_qwen_vl_model, ChatQwenVL

    return create_qwen_vl_model()


def get_vision_model_config() -> dict:
    """获取视觉模型配置。"""
    return {
        "provider": "qwen-vl",  # 当前使用 Qwen VL
        "model": "qwen-vl-plus",
        "supports_vision": True,
    }
