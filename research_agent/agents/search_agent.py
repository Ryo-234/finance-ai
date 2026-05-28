"""搜索 Agent - 网络信息检索。"""

from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage


class SearchAgent(BaseAgent):
    """搜索 Agent - 从网络获取最新信息。

    支持多种搜索提供商：
    - Tavily（推荐，高质量结果）
    - DuckDuckGo（免费，无需 API Key）
    """

    def __init__(self, model=None, provider: str = "tavily"):
        """初始化搜索 Agent。

        参数：
            model: 聊天模型实例
            provider: 搜索提供商 ("tavily" / "duckduckgo")
        """
        super().__init__(
            config=AgentConfig(
                name="search",
                description="搜索 Agent - 从网络获取最新信息",
                model=model,
                system_prompt="""你是一个专业的研究搜索助手。

你的职责：
1. 根据给定的主题执行网络搜索
2. 分析搜索结果，提取关键信息
3. 对结果进行总结和整理

请注意：
- 只返回真实、有来源的信息
- 注明信息来源
- 保持客观中立的语气""",
            )
        )
        self.provider = provider

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行搜索并返回结果。"""
        # 统一转换为字典
        state_dict = state_to_dict(state)

        if query is None:
            # 从状态或任务中获取查询
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        # 根据提供商执行搜索
        if self.provider == "tavily":
            results = await self._search_tavily(query)
        else:
            results = await self._search_duckduckgo(query)

        return {
            **state_dict,
            "search_results": results,
            "search_query": query,
        }

    async def _search_tavily(self, query: str) -> str:
        """使用 Tavily API 执行搜索。"""
        try:
            from community.tavily_search import tavily_search

            results = await tavily_search(query, max_results=5)
            return self._format_results(results)
        except ImportError:
            return "Tavily 未安装，请运行: pip install tavily-python"

    async def _search_duckduckgo(self, query: str) -> str:
        """使用 DuckDuckGo 执行搜索。"""
        try:
            from community.duckduckgo_search import duckduckgo_search

            results = await duckduckgo_search(query, max_results=5)
            return self._format_results(results)
        except ImportError:
            return "DuckDuckGo 搜索未安装"

    def _format_results(self, results: list) -> str:
        """格式化搜索结果。"""
        if not results:
            return "未找到相关结果"

        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "无标题")
            url = result.get("url", "")
            content = result.get("content", "")[:200]
            formatted.append(f"[{i}] {title}\nURL: {url}\n摘要: {content}...")

        return "\n\n".join(formatted)