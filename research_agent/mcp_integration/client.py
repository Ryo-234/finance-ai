"""MCP 客户端 - 构建服务器参数。"""

import logging
from typing import Any, Dict, Optional

from config.mcp import McpConfig, McpServerConfig

logger = logging.getLogger(__name__)


def build_server_params(server_name: str, config: McpServerConfig) -> Dict[str, Any]:
    """构建单个 MCP 服务器的参数。

    Args:
        server_name: MCP 服务器名称
        config: 服务器配置

    Returns:
        适用于 langchain-mcp-adapters 的参数字典
    """
    transport_type = config.type or "stdio"
    params: Dict[str, Any] = {"transport": transport_type}

    if transport_type == "stdio":
        if not config.command:
            raise ValueError(
                f"MCP 服务器 '{server_name}' 使用 stdio 传输时需要指定 'command' 字段"
            )
        params["command"] = config.command
        params["args"] = config.args or []
        # 添加环境变量
        if config.env:
            params["env"] = config.env

    elif transport_type in ("sse", "http"):
        if not config.url:
            raise ValueError(
                f"MCP 服务器 '{server_name}' 使用 {transport_type} 传输时需要指定 'url' 字段"
            )
        params["url"] = config.url
        # 添加请求头
        if config.headers:
            params["headers"] = config.headers

    else:
        raise ValueError(
            f"MCP 服务器 '{server_name}' 的传输类型 '{transport_type}' 不支持"
        )

    return params


def build_servers_config(mcp_config: McpConfig) -> Dict[str, Dict[str, Any]]:
    """构建所有已启用 MCP 服务器的配置。

    Args:
        mcp_config: MCP 全局配置

    Returns:
        服务器名称到参数的映射字典
    """
    servers_config = {}

    for server_name, server_config in mcp_config.servers.items():
        if not server_config.enabled:
            logger.debug(f"MCP 服务器 '{server_name}' 未启用，跳过")
            continue

        try:
            servers_config[server_name] = build_server_params(server_name, server_config)
            logger.info(f"已配置 MCP 服务器: {server_name}")
        except Exception as e:
            logger.error(f"配置 MCP 服务器 '{server_name}' 失败: {e}")

    return servers_config


def get_enabled_servers_count(mcp_config: McpConfig) -> int:
    """获取已启用的 MCP 服务器数量。"""
    return sum(1 for cfg in mcp_config.servers.values() if cfg.enabled)
