"""FastAPI 应用 - Research Agent Gateway API。"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import threads, chat, memory, models, health, channels
from graph.research_graph import set_middleware_manager
from middleware.factory import get_default_middleware_manager
from middleware.auth import AuthMiddleware
from tools.registry import get_tool_registry
from channels.service import init_channels, shutdown_channels

logger = logging.getLogger(__name__)


class 请求追踪中间件(BaseHTTPMiddleware):
    """X-Request-ID 中间件 —— 为每个请求生成或透传追踪 ID。"""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


def load_config() -> dict:
    """从 config.yaml 加载配置。"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        logger.warning(f"配置文件不存在: {config_path}")
        return {}

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动时初始化
    logger.info("Research Agent Gateway 启动中...")

    # 初始化数据库
    try:
        from db.database import init_db
        init_db()
        logger.info("数据库已初始化")
    except Exception as e:
        logger.warning(f"数据库初始化跳过: {e}")

    # 初始化金融数据源
    try:
        from data_sources.registry import get_registry
        from data_sources.eastmoney import EastMoneyDataSource, EastMoneyFreeDataSource
        from data_sources.sina_finance import SinaFinanceDataSource

        ds_registry = get_registry()
        ds_registry.register(EastMoneyFreeDataSource())
        ds_registry.register(EastMoneyDataSource())
        ds_registry.register(SinaFinanceDataSource())
        logger.info(f"金融数据源已注册: {ds_registry.list_all()}")
    except Exception as e:
        logger.warning(f"金融数据源初始化跳过: {e}")

    # 初始化中间件管理器
    middleware_manager = get_default_middleware_manager()
    set_middleware_manager(middleware_manager)
    logger.info(f"中间件已初始化，启用 {len(middleware_manager.list_middlewares())} 个中间件")

    # 初始化工具注册表
    registry = get_tool_registry()
    logger.info(f"工具注册表已初始化: {len(registry.list_tools())} 个工具")

    # 初始化 MCP 工具
    try:
        from mcp_integration.tools import get_mcp_tools
        from config.mcp import get_mcp_config
        mcp_config = get_mcp_config()
        if mcp_config.enabled:
            mcp_tools = await get_mcp_tools(mcp_config)
            if mcp_tools:
                registry.set_mcp_tools(mcp_tools)
                logger.info(f"MCP 工具已加载: {len(mcp_tools)} 个")
    except Exception as e:
        logger.warning(f"MCP 初始化跳过: {e}")

    # 从 config.yaml 读取 IM 渠道配置
    config = load_config()
    feishu_config = config.get("feishu", {})

    if feishu_config.get("enabled", False):
        channel_config = {
            "feishu": {
                "enabled": True,
                "app_id": feishu_config.get("app_id"),
                "app_secret": feishu_config.get("app_secret"),
                "bot_name": feishu_config.get("bot_name", "DeerFlow Bot"),
                "allowed_users": feishu_config.get("allowed_users", []),
            },
        }
        try:
            await init_channels(channel_config)
            logger.info("飞书渠道初始化成功")
        except Exception as e:
            logger.warning(f"飞书渠道初始化失败: {e}")
    else:
        logger.info("飞书渠道未启用")

    yield

    # 关闭时清理
    logger.info("Research Agent Gateway 关闭中...")
    await shutdown_channels()


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(
        title="Research Agent API",
        description="""
## Research Agent API Gateway

智能研究助手的 API 网关，提供：

- **聊天接口** - 与 Agent 对话，支持流式响应
- **线程管理** - 管理对话历史
- **记忆系统** - 访问和管理用户记忆
- **模型配置** - 查看可用模型

### 核心概念

**线程 (Thread)**：一次对话会话，每个线程有独立的 ID

**消息 (Message)**：对话中的单条消息，包含用户输入和 AI 回复
        """,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # X-Request-ID 请求追踪
    app.add_middleware(请求追踪中间件)

    # API Key 认证中间件
    app.add_middleware(AuthMiddleware)

    # 注册路由
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(threads.router, tags=["threads"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(memory.router, tags=["memory"])
    app.include_router(models.router, tags=["models"])
    app.include_router(channels.router, tags=["channels"])

    # 注册金融投研路由
    from .routers import auth, reports, billing, tasks
    app.include_router(auth.router, tags=["auth"])
    app.include_router(reports.router, tags=["reports"])
    app.include_router(billing.router, tags=["billing"])
    app.include_router(tasks.router, tags=["tasks"])

    return app


# 创建应用实例
app = create_app()