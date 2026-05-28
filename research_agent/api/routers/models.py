"""模型管理路由。"""

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


@router.get("/", response_model=ModelsResponse)
async def list_models():
    """列出可用模型。

    返回系统中配置的所有模型。
    """
    # 这里应该从配置读取实际模型
    # 目前硬编码一些默认值

    models = [
        ModelInfo(
            name="qwen-plus",
            display_name="通义千文 Plus",
            provider="aliyun",
            status="active",
        ),
        ModelInfo(
            name="qwen-turbo",
            display_name="通义千文 Turbo",
            provider="aliyun",
            status="active",
        ),
        ModelInfo(
            name="gpt-4",
            display_name="GPT-4",
            provider="openai",
            status="active",
        ),
    ]

    return ModelsResponse(
        models=models,
        default_model="qwen-plus",
    )


@router.get("/{model_name}")
async def get_model(model_name: str):
    """获取特定模型详情。"""
    # 简化实现
    models = {
        "qwen-plus": {
            "name": "qwen-plus",
            "display_name": "通义千文 Plus",
            "provider": "aliyun",
            "status": "active",
            "context_window": 128000,
        },
        "qwen-turbo": {
            "name": "qwen-turbo",
            "display_name": "通义千文 Turbo",
            "provider": "aliyun",
            "status": "active",
            "context_window": 128000,
        },
        "gpt-4": {
            "name": "gpt-4",
            "display_name": "GPT-4",
            "provider": "openai",
            "status": "active",
            "context_window": 128000,
        },
    }

    if model_name not in models:
        return {"error": f"Model {model_name} not found"}

    return models[model_name]