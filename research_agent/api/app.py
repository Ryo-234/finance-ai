"""FastAPI 应用 - Research Agent Gateway API。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import threads, chat, memory, models, health, channels
from graph.research_graph import set_middleware_manager
from middleware.factory import get_default_middleware_manager
from tools.registry import get_tool_registry
from channels.service import init_channels, shutdown_channels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动时初始化
    logger.info("Research Agent Gateway 启动中...")

    # 初始化中间件管理器
    middleware_manager = get_default_middleware_manager()
    set_middleware_manager(middleware_manager)
    logger.info(f"中间件已初始化，启用 {len(middleware_manager.list_middlewares())} 个中间件")

    # 初始化工具注册表
    registry = get_tool_registry()
    logger.info(f"工具注册表已初始化: {len(registry.list_tools())} 个工具")

    # 初始化 IM 渠道（从配置读取）
    channel_config = {
        "feishu": {
            "enabled": True,  # 已配置完成，开启
            "app_id": "cli_aa8f12dd26789bcb",
            "app_secret": "l9zilEnsFlLo7rie4EuRfgid7eRDljPn",
            "bot_name": "Research_agent",
        },
    }
    try:
        await init_channels(channel_config)
    except Exception as e:
        logger.warning(f"渠道初始化失败（不影响 API 服务）: {e}")

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
        allow_origins=["*"],  # 生产环境应该限制
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(threads.router, prefix="/api/threads", tags=["threads"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(models.router, prefix="/api/models", tags=["models"])
    app.include_router(channels.router, prefix="/api/channels", tags=["channels"])

    return app


# 创建应用实例
app = create_app()