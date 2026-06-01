"""模型管理路由 —— 根据当前提供商动态返回可用模型。"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelInfo(BaseModel):
    """模型信息。"""
    name: str = Field(..., description="模型名称")
    display_name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="提供商")
    status: str = Field(default="active", description="状态")


class ModelsResponse(BaseModel):
    """模型列表响应。"""
    models: list[ModelInfo]
    default_model: str


# 按提供商标注册表的模型定义
_提供商标注册表 = {
    "qwen": {
        "models": [
            {"name": "qwen-plus", "display_name": "通义千问 Plus", "context_window": 131072},
            {"name": "qwen-turbo", "display_name": "通义千问 Turbo", "context_window": 131072},
            {"name": "qwen-max", "display_name": "通义千问 Max", "context_window": 32768},
        ],
        "provider_name": "aliyun",
    },
    "minimax": {
        "models": [
            {"name": "MiniMax-M2.7-highspeed", "display_name": "MiniMax M2.7 高速版", "context_window": 245760},
            {"name": "MiniMax-M2.7", "display_name": "MiniMax M2.7", "context_window": 245760},
        ],
        "provider_name": "minimax",
    },
}


def _get_current_models() -> tuple[list[dict], str, str]:
    """根据当前配置的提供商返回模型列表和默认模型名。

    返回：
        (模型列表, 默认模型名, 提供商显示名)
    """
    from config.models import get_model_config

    config = get_model_config()
    provider = config.provider

    注册 = _提供商标注册表.get(provider, _提供商标注册表["qwen"])
    models = 注册["models"]
    提供商名 = 注册["provider_name"]
    默认名 = config.default_model

    # 确保默认模型在列表中
    if not any(m["name"] == 默认名 for m in models):
        默认名 = models[0]["name"] if models else "unknown"

    return models, 默认名, 提供商名


@router.get("/", response_model=ModelsResponse)
async def list_models():
    """列出当前提供商下的可用模型。"""
    models_data, 默认名, 提供商名 = _get_current_models()

    models = [
        ModelInfo(
            name=m["name"],
            display_name=m["display_name"],
            provider=提供商名,
            status="active",
        )
        for m in models_data
    ]

    return ModelsResponse(
        models=models,
        default_model=默认名,
    )


@router.get("/{model_name}")
async def get_model(model_name: str):
    """获取特定模型详情。"""
    models_data, _, 提供商名 = _get_current_models()

    for m in models_data:
        if m["name"] == model_name:
            return {
                "name": m["name"],
                "display_name": m["display_name"],
                "provider": 提供商名,
                "status": "active",
                "context_window": m["context_window"],
            }

    return {"error": f"模型 {model_name} 未找到"}