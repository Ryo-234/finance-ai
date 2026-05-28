"""搜索工具。"""

from typing import Dict, Any, Optional


class SearchTool:
    """搜索工具 - 封装搜索功能。"""

    def __init__(self):
        """初始化搜索工具。"""
        self.name = "search"
        self.description = "从网络搜索最新信息"
        self.parameters = {
            "query": {
                "type": "string",
                "description": "搜索查询语句",
                "required": True,
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数",
                "default": 5,
            },
        }

    async def search(self, query: str, max_results: int = 5, provider: str = "tavily") -> Dict[str, Any]:
        """执行搜索。

        参数：
            query: 搜索查询
            max_results: 最大结果数
            provider: 搜索提供商

        返回：
            搜索结果字典
        """
        if provider == "tavily":
            from community.tavily_search import tavily_search
            results = await tavily_search(query, max_results)
        else:
            from community.duckduckgo_search import duckduckgo_search
            results = await duckduckgo_search(query, max_results)

        return {
            "query": query,
            "provider": provider,
            "results": results,
            "count": len(results),
        }