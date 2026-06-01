"""认证中间件 —— 支持 JWT Token 和 API Key 两种认证方式。

白名单路径跳过认证（/docs, /redoc, /openapi.json, /api/health）。
JWT 用于用户登录认证，API Key 用于服务间调用。
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# JWT 配置
JWT_SECRET = os.environ.get("JWT_SECRET", "finance-agent-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72

# 无需认证的路径前缀
_SKIP_PATHS = {
    "/docs", "/redoc", "/openapi.json", "/api/health",
    "/api/auth/register", "/api/auth/login",
}


def _load_valid_tokens() -> List[str]:
    """从环境变量加载有效 API 令牌列表。"""
    keys_env = os.getenv("API_KEYS", "")
    if keys_env:
        return [k.strip() for k in keys_env.split(",") if k.strip()]
    single_key = os.getenv("API_KEY", "")
    if single_key:
        return [single_key.strip()]
    return []


def create_token(user_id: str, plan_type: str = "free") -> str:
    """创建 JWT Token。"""
    payload = {
        "user_id": user_id,
        "plan_type": plan_type,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT Token。"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 —— JWT + API Key 双模式。

    优先级：JWT > API Key > 默认访客。
    未配置任何认证时，分配默认访客身份。
    """

    def __init__(self, app, valid_tokens: List[str] | None = None):
        super().__init__(app)
        self._valid_tokens = valid_tokens if valid_tokens is not None else _load_valid_tokens()
        if self._valid_tokens:
            logger.info(f"认证中间件已启用，加载了 {len(self._valid_tokens)} 个有效 API 令牌")
        else:
            logger.info("未配置 API_KEYS，使用 JWT 或无认证模式")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 白名单路径跳过认证
        for skip_path in _SKIP_PATHS:
            if path == skip_path or path.startswith(skip_path):
                request.state.user_id = ""
                request.state.plan_type = "free"
                return await call_next(request)

        # OPTIONS 预检放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 提取 Token
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # 1. 尝试 JWT 解码
        if token:
            try:
                payload = decode_token(token)
                request.state.user_id = payload.get("user_id", "default_user")
                request.state.plan_type = payload.get("plan_type", "free")
                return await call_next(request)
            except Exception:
                pass

            # 2. 尝试 API Key 匹配
            if self._valid_tokens and token in self._valid_tokens:
                request.state.user_id = "api_user"
                request.state.plan_type = "pro"
                return await call_next(request)

            # Token 无效
            if self._valid_tokens:
                logger.warning(f"无效的认证令牌: {path}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "认证令牌无效"},
                )

        # 3. 无 Token —— 分配默认访客身份
        request.state.user_id = "default_user"
        request.state.plan_type = "free"
        return await call_next(request)
