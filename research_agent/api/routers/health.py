"""健康检查路由。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查端点。

    返回服务健康状态。
    """
    return {
        "status": "healthy",
        "service": "research-agent-gateway",
        "version": "1.0.0",
    }