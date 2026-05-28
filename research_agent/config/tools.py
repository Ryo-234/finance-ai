"""工具配置模块。"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class ToolsConfig:
    """工具配置类。"""

    # 是否启用搜索工具
    search_enabled: bool = True
    # 搜索工具类型：tavily / duckduckgo
    search_provider: str = "tavily"
    # Tavily API Key
    tavily_api_key: Optional[str] = None


_config: Optional[ToolsConfig] = None


def get_tools_config() -> ToolsConfig:
    """获取工具配置单例。"""
    global _config
    if _config is None:
        _config = ToolsConfig(
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
        )
    return _config