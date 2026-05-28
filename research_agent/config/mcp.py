"""MCP (Model Context Protocol) 配置模块。"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class McpOAuthConfig:
    """OAuth 配置。"""

    enabled: bool = False
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_endpoint: Optional[str] = None
    auth_type: str = "client_credentials"  # client_credentials, refresh_token


@dataclass
class McpServerConfig:
    """MCP 服务器配置。"""

    enabled: bool = False
    type: str = "stdio"  # stdio, sse, http
    command: Optional[str] = None
    args: list = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    oauth: Optional[McpOAuthConfig] = None
    description: str = ""


@dataclass
class McpConfig:
    """MCP 全局配置。"""

    enabled: bool = True
    servers: Dict[str, McpServerConfig] = field(default_factory=dict)
    # 自定义拦截器路径列表，格式: "pkg.module:builder_func"
    interceptors: list = field(default_factory=list)


_config: Optional[McpConfig] = None


def _resolve_env_var(value: str) -> str:
    """解析环境变量引用。

    支持格式: ${VAR_NAME} 或 $VAR_NAME
    """
    if not isinstance(value, str):
        return value

    if value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.getenv(var_name, "")
    elif value.startswith("$"):
        var_name = value[1:]
        return os.getenv(var_name, "")

    return value


def _parse_mcp_config(config_dict: Dict[str, Any]) -> Dict[str, McpServerConfig]:
    """解析 MCP 服务器配置字典。"""
    servers = {}

    if config_dict is None:
        return servers

    for server_name, server_data in config_dict.items():
        if isinstance(server_data, dict):
            oauth_data = server_data.pop("oauth", None)
            oauth_config = None
            if oauth_data and isinstance(oauth_data, dict):
                oauth_config = McpOAuthConfig(
                    enabled=oauth_data.get("enabled", False),
                    client_id=oauth_data.get("client_id"),
                    client_secret=_resolve_env_var(oauth_data.get("client_secret", "")),
                    token_endpoint=oauth_data.get("token_endpoint"),
                    auth_type=oauth_data.get("auth_type", "client_credentials"),
                )

            # 解析环境变量
            env = {}
            for k, v in server_data.get("env", {}).items():
                env[k] = _resolve_env_var(v)

            servers[server_name] = McpServerConfig(
                enabled=server_data.get("enabled", False),
                type=server_data.get("type", "stdio"),
                command=server_data.get("command"),
                args=server_data.get("args", []),
                env=env,
                url=server_data.get("url"),
                headers=server_data.get("headers", {}),
                oauth=oauth_config,
                description=server_data.get("description", ""),
            )

    return servers


def get_mcp_config() -> McpConfig:
    """获取 MCP 配置单例。"""
    global _config

    if _config is None:
        _config = _load_mcp_config()

    return _config


def _load_mcp_config() -> McpConfig:
    """从配置文件加载 MCP 配置。"""
    import yaml

    config_path = os.getenv("RESEARCH_AGENT_CONFIG_PATH", "config.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"配置文件 {config_path} 未找到，使用默认配置")
        return McpConfig()

    mcp_data = config_data.get("mcp", {})

    return McpConfig(
        enabled=mcp_data.get("enabled", True),
        servers=_parse_mcp_config(mcp_data.get("servers", {})),
        interceptors=mcp_data.get("interceptors", []),
    )


def reload_mcp_config() -> McpConfig:
    """重新加载 MCP 配置。"""
    global _config
    _config = _load_mcp_config()
    return _config
