"""MCP (Model Context Protocol) 集成模块。

提供 MCP 工具的加载、管理和执行功能。
参考 deer-flow 的 MCP 实现设计。
"""

from .client import build_server_params, build_servers_config
from .tools import get_mcp_tools, initialize_mcp_tools, get_cached_mcp_tools, reset_mcp_tools_cache
from config.mcp import McpConfig, McpServerConfig, McpOAuthConfig, get_mcp_config, reload_mcp_config

__all__ = [
    # 客户端
    "build_server_params",
    "build_servers_config",
    # 工具加载
    "get_mcp_tools",
    "initialize_mcp_tools",
    "get_cached_mcp_tools",
    "reset_mcp_tools_cache",
    # 配置
    "McpConfig",
    "McpServerConfig",
    "McpOAuthConfig",
    "get_mcp_config",
    "reload_mcp_config",
]
