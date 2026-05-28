"""MCP 工具加载模块 - 使用 langchain-mcp-adapters。"""

import asyncio
import atexit
import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any, List, Optional

from langchain_core.tools import BaseTool

from research_agent.config.mcp import McpConfig, get_mcp_config
from .client import build_servers_config

logger = logging.getLogger(__name__)

# 全局线程池，用于在异步环境中同步执行工具
_SYNC_TOOL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=10, thread_name_prefix="mcp-sync-tool"
)

# 注册关闭钩子
atexit.register(lambda: _SYNC_TOOL_EXECUTOR.shutdown(wait=False))

# 缓存
_mcp_tools_cache: Optional[List[BaseTool]] = None
_cache_config_mtime: float = 0.0


def _make_sync_tool_wrapper(coro: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
    """为异步工具协程构建同步包装器。

    Args:
        coro: 工具的异步协程
        tool_name: 工具名称（用于日志）

    Returns:
        正确处理嵌套事件循环的同步函数
    """

    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is not None and loop.is_running():
                # 使用全局执行器避免嵌套循环问题
                future = _SYNC_TOOL_EXECUTOR.submit(asyncio.run, coro(*args, **kwargs))
                return future.result()
            else:
                return asyncio.run(coro(*args, **kwargs))
        except Exception as e:
            logger.error(f"同步调用 MCP 工具 '{tool_name}' 时出错: {e}", exc_info=True)
            raise

    return sync_wrapper


async def get_mcp_tools(mcp_config: Optional[McpConfig] = None) -> List[BaseTool]:
    """获取所有已启用 MCP 服务器的工具。

    Args:
        mcp_config: MCP 配置，不提供则从配置文件加载

    Returns:
        所有 MCP 服务器的 LangChain 工具列表
    """
    if mcp_config is None:
        mcp_config = get_mcp_config()

    if not mcp_config.enabled:
        logger.info("MCP 功能已禁用")
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning(
            "langchain-mcp-adapters 未安装。安装以启用 MCP 工具: "
            "pip install langchain-mcp-adapters"
        )
        return []

    servers_config = build_servers_config(mcp_config)

    if not servers_config:
        logger.info("没有已启用的 MCP 服务器")
        return []

    try:
        logger.info(f"正在初始化 MCP 客户端，共 {len(servers_config)} 个服务器")

        # 创建多服务器 MCP 客户端
        # tool_name_prefix=True 确保工具名不冲突
        client = MultiServerMCPClient(servers_config, tool_name_prefix=True)

        # 获取所有工具
        tools = await client.get_tools()
        logger.info(f"成功从 MCP 服务器加载 {len(tools)} 个工具")

        # 为工具添加同步调用支持
        for tool in tools:
            if getattr(tool, "func", None) is None and getattr(tool, "coroutine", None) is not None:
                tool.func = _make_sync_tool_wrapper(tool.coroutine, tool.name)

        return tools

    except Exception as e:
        logger.error(f"加载 MCP 工具失败: {e}", exc_info=True)
        return []


def initialize_mcp_tools() -> List[BaseTool]:
    """同步初始化 MCP 工具。

    Returns:
        工具列表
    """
    return asyncio.run(get_mcp_tools())


def get_cached_mcp_tools(mcp_config: Optional[McpConfig] = None) -> List[BaseTool]:
    """获取缓存的 MCP 工具（如果配置未变更）。

    Args:
        mcp_config: MCP 配置

    Returns:
        缓存的工具列表或新加载的工具
    """
    global _mcp_tools_cache, _cache_config_mtime

    if mcp_config is None:
        mcp_config = get_mcp_config()

    # 检查配置是否变更
    import os

    config_path = os.getenv("RESEARCH_AGENT_CONFIG_PATH", "config.yaml")
    try:
        current_mtime = os.path.getmtime(config_path)
    except OSError:
        current_mtime = 0

    if _mcp_tools_cache is None or _cache_config_mtime != current_mtime:
        logger.info("MCP 配置已变更，重新加载工具")
        _mcp_tools_cache = initialize_mcp_tools()
        _cache_config_mtime = current_mtime

    return _mcp_tools_cache


def reset_mcp_tools_cache() -> None:
    """重置 MCP 工具缓存。"""
    global _mcp_tools_cache, _cache_config_mtime
    _mcp_tools_cache = None
    _cache_config_mtime = 0.0
    logger.info("MCP 工具缓存已重置")
