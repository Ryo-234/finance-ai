"""知识库 Agent - 通过 MCP 工具和已有信息进行知识检索。

该 Agent 整合多个数据源：
1. RAG 检索结果（来自上一个节点）
2. MCP 外部工具（如果已配置）
3. 网络搜索结果（来自上一个节点）
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get

logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    """知识库 Agent - 整合多源知识。

    工作方式：
    1. 检查 RAG 节点已检索到的文档
    2. 尝试调用 MCP 工具执行额外查询
    3. 汇总所有知识源的结果

    注意：该 Agent 优先使用已有信息，MCP 工具作为补充。
    """

    def __init__(self, model=None):
        super().__init__(
            config=AgentConfig(
                name="knowledge",
                description="知识库 Agent - 整合 RAG、MCP 和搜索结果",
                model=model,
                system_prompt="""你是一个知识整合助手。

你的职责：
1. 整合 RAG 检索到的文档信息
2. 调用可用的 MCP 工具获取补充数据
3. 汇总网络搜索结果
4. 提供结构化的知识输出

可用的数据源：
- RAG 向量检索（本地文档）
- MCP 外部工具（文件系统、数据库等）
- 网络搜索（Tavily/DuckDuckGo）
- 对话历史中的上下文信息""",
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行知识检索，整合多个数据源。

        返回包含 knowledge_results 的状态更新。
        """
        state_dict = state_to_dict(state)

        if query is None:
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        results_parts = []

        # 数据源 1：RAG 检索结果
        rag_results = state_dict.get("rag_results", [])
        if rag_results:
            results_parts.append("## 本地文档检索\n")
            for i, doc in enumerate(rag_results[:3], 1):
                source = doc.get("source", "未知来源")
                content = doc.get("content", "")[:300]
                results_parts.append(f"{i}. [{source}] {content}")
            results_parts.append("")

        # 数据源 2：MCP 工具查询
        mcp_results = await self._query_mcp_tools(query, state_dict)
        if mcp_results:
            results_parts.append("## MCP 工具查询\n")
            results_parts.append(mcp_results)
            results_parts.append("")

        # 数据源 3：网络搜索结果（来自 search 节点）
        search_results = state_dict.get("search_results", "")
        if search_results:
            results_parts.append("## 网络搜索\n")
            results_parts.append(str(search_results)[:500])
            results_parts.append("")

        knowledge_text = "\n".join(results_parts) if results_parts else f"暂无结构化知识库数据，查询: {query}"

        return {
            **state_dict,
            "knowledge_query": query,
            "knowledge_results": knowledge_text,
        }

    async def _query_mcp_tools(self, query: str, state_dict: dict) -> str:
        """尝试通过 MCP 工具获取信息。

        遍历已注册的 MCP 工具，找到匹配的工具并执行查询。
        """
        try:
            from tools.registry import get_tool_registry
            registry = get_tool_registry()
            mcp_tools = registry.list_mcp_tools() if hasattr(registry, 'list_mcp_tools') else []
        except Exception as e:
            logger.warning("获取 MCP 工具失败: %s", e)
            return ""

        if not mcp_tools:
            return ""

        # 对每个 MCP 工具尝试执行
        results = []
        for tool_def in mcp_tools:
            tool_name = tool_def.get("name", "unknown") if isinstance(tool_def, dict) else getattr(tool_def, "name", "unknown")
            tool_func = tool_def.get("func") if isinstance(tool_def, dict) else getattr(tool_def, "func", None)

            if tool_func is None:
                continue

            try:
                logger.info("调用 MCP 工具: %s，查询: %s", tool_name, query[:80])
                result = tool_func(query)
                if result and str(result).strip():
                    results.append(f"### {tool_name}\n{str(result)[:500]}")
            except Exception as e:
                logger.warning("MCP 工具 %s 执行失败: %s", tool_name, e)

        return "\n\n".join(results) if results else ""


def create_knowledge_agent(model=None) -> KnowledgeAgent:
    """创建 Knowledge Agent 工厂函数。"""
    return KnowledgeAgent(model=model)
