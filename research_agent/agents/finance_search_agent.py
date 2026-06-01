"""金融搜索 Agent —— 从多个金融数据源获取行情、新闻、公告。"""

import logging
from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from data_sources.registry import get_registry
from compliance.source_tracker import SourceTracker
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class FinanceSearchAgent(BaseAgent):
    """金融搜索 Agent —— 多数据源金融信息检索。

    替代原 SearchAgent，专门处理金融领域数据获取：
    - 东方财富（行情、新闻、公告）
    - 新浪财经（新闻、基本面）
    - 巨潮资讯（上市公司公告）
    """

    def __init__(self, model=None):
        super().__init__(
            config=AgentConfig(
                name="finance_search",
                description="金融搜索 Agent - 从多数据源获取金融信息",
                model=model,
                system_prompt="""你是一个金融信息检索助手。

你的职责：
1. 从多个金融数据源获取信息（行情、新闻、公告、研报）
2. 按相关性排序和去重
3. 标注每条信息的来源和时间

数据来源：东方财富、新浪财经、巨潮资讯""",
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行金融数据搜索。"""
        state_dict = state_to_dict(state)

        if query is None:
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        plan_type = state_get(state_dict, "plan_type", "free")
        report_type = state_get(state_dict, "report_type", "")
        user_id = state_get(state_dict, "user_id", "")

        # 初始化来源追踪器
        tracker = SourceTracker()

        # 性能优化：金融数据源 + 通用网络搜索并发执行
        import asyncio
        registry = get_registry()
        docs_task = registry.search_merged(
            query=query,
            plan_type=plan_type,
            report_type=report_type,
            max_total=15,
        )
        web_task = self._search_web(query)
        docs, web_results = await asyncio.gather(docs_task, web_task, return_exceptions=True)

        # 异常降级
        if isinstance(docs, Exception):
            logger.warning(f"金融数据源搜索异常: {docs}")
            docs = []
        if isinstance(web_results, Exception):
            logger.warning(f"网络搜索异常: {web_results}")
            web_results = ""

        # 记录来源
        tracker.track_docs(docs)

        # 格式化结果
        financial_data = self._format_financial_results(docs)
        search_results = self._format_combined_results(financial_data, web_results)

        result = {
            **state_dict,
            "search_results": search_results,
            "financial_data": {
                "documents": [d.to_dict() for d in docs],
                "source_count": len(docs),
                "query": query,
            },
            "search_query": query,
        }

        return result

    async def _search_web(self, query: str) -> str:
        """通用网络搜索作为补充。"""
        try:
            from community.tavily_search import tavily_search
            results = await tavily_search(query, max_results=5)
            return self._format_web_results(results)
        except Exception:
            try:
                from community.duckduckgo_search import duckduckgo_search
                results = await duckduckgo_search(query, max_results=5)
                return self._format_web_results(results)
            except Exception:
                return ""

    def _format_financial_results(self, docs: list) -> str:
        """格式化金融数据源结果。"""
        if not docs:
            return ""

        lines = ["## 金融数据源结果\n"]
        for i, doc in enumerate(docs, 1):
            source_tag = f"[{doc.source_name}]"
            lines.append(
                f"### {i}. {doc.title} {source_tag}\n"
                f"- 类型：{doc.doc_type}\n"
                f"- 时间：{doc.publish_time}\n"
                f"- 来源：{doc.source_url}\n"
                f"- 内容：{doc.content[:300]}\n"
            )

        return "\n".join(lines)

    def _format_web_results(self, results: list) -> str:
        """格式化网络搜索结果。"""
        if not results:
            return ""

        lines = ["\n## 网络搜索结果\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            url = r.get("url", "")
            content = r.get("content", "")[:200]
            lines.append(f"[{i}] **{title}**\n    URL: {url}\n    > {content}\n")

        return "\n".join(lines)

    def _format_combined_results(self, financial: str, web: str) -> str:
        """合并金融数据和网络搜索结果。"""
        parts = []
        if financial:
            parts.append(financial)
        if web:
            parts.append(web)
        return "\n".join(parts) if parts else "未找到相关结果"
