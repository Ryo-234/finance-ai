"""API Key 认证中间件 —— HTTP 层面的 Bearer Token 校验。

白名单路径跳过认证（/docs, /redoc, /openapi.json, /api/health）。
有效令牌从环境变量 API_KEYS（逗号分隔）或 API_KEY（单个）读取。
"""

import logging
import os
from typing import List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# 无需认证的路径前缀
_SKIP_PATHS = {
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
}


def _load_valid_tokens() -> List[str]:
    """从环境变量加载有效令牌列表。"""
    # 优先读取 API_KEYS（逗号分隔多个）
    keys_env = os.getenv("API_KEYS", "")
    if keys_env:
        return [k.strip() for k in keys_env.split(",") if k.strip()]

    # 回退到 API_KEY（单个）
    single_key = os.getenv("API_KEY", "")
    if single_key:
        return [single_key.strip()]

    return []


class AuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件。

    检查请求头 Authorization: Bearer <token>。
    如果未配置任何有效令牌，则放行所有请求（兼容开发环境）。
    """

    def __init__(self, app, valid_tokens: List[str] | None = None):
        """初始化认证中间件。

        参数：
            app: FastAPI 应用实例
            valid_tokens: 有效令牌列表，为 None 时自动从环境变量加载
        """
        super().__init__(app)
        self._valid_tokens = valid_tokens if valid_tokens is not None else _load_valid_tokens()
        if self._valid_tokens:
            logger.info(f"认证中间件已启用，加载了 {len(self._valid_tokens)} 个有效令牌")
        else:
            logger.warning("未配置 API_KEYS 或 API_KEY，认证中间件处于放行模式")

    async def dispatch(self, request: Request, call_next):
        """处理每个 HTTP 请求。

        参数：
            request: 请求对象
            call_next: 下一个中间件或路由处理器

        返回：
            响应对象
        """
        # 白名单路径跳过认证
        path = request.url.path
        for skip_path in _SKIP_PATHS:
            if path == skip_path or path.startswith(skip_path):
                return await call_next(request)

        # 未配置令牌则放行（开发模式）
        if not self._valid_tokens:
            return await call_next(request)

        # 检查 Authorization 头
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning(f"请求缺少 Authorization 头: {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "缺少认证令牌，请提供 Authorization: Bearer <token>"},
            )

        token = auth_header[7:]  # 去掉 "Bearer " 前缀
        if token not in self._valid_tokens:
            logger.warning(f"无效的认证令牌: {request.url.path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "认证令牌无效"},
            )

        return await call_next(request)
