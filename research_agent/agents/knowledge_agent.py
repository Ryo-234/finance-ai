"""知识库 Agent - 通过 MCP 连接数据库进行知识检索。

该 Agent 通过 MCP 协议连接外部数据库，支持：
1. 结构化数据查询
2. 全文检索
3. 复杂数据分析

不再使用向量检索，而是通过 MCP 工具直接查询数据库。
"""

from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage


class KnowledgeAgent(BaseAgent):
    """知识库 Agent - 通过 MCP/数据库查询获取信息。

    功能：
    1. 通过 MCP 工具连接数据库
    2. 执行结构化查询
    3. 返回精确的查询结果

    注意：该 Agent 依赖于 MCP 服务器配置的数据库工具。
    如果没有配置数据库 MCP 服务器，该 Agent 无法工作。
    """

    def __init__(self, model=None):
        """初始化知识库 Agent。

        参数：
            model: 聊天模型实例
        """
        super().__init__(
            config=AgentConfig(
                name="knowledge",
                description="知识库 Agent - 通过数据库查询获取信息",
                model=model,
                system_prompt="""你是一个知识库查询助手。

你的职责：
1. 通过 MCP 工具查询数据库获取信息
2. 执行结构化数据查询
3. 提供准确的查询结果

可用的 MCP 数据库工具：
- SQL 查询工具（如 postgres-mcp, mysql-mcp）
- MongoDB 查询工具
- Redis 查询工具
- 自定义 API 工具

请注意：
- 使用精确的查询条件，避免全表扫描
- 合理利用索引优化查询
- 返回结果要包含数据来源说明""",
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从知识库检索信息（通过 MCP 数据库工具）。

        参数：
            state: 当前状态
            query: 查询语句（可选）

        返回：
            更新后的状态
        """
        state_dict = state_to_dict(state)

        if query is None:
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        # 该 Agent 的工作方式是通过 MCP 工具直接查询
        # 不在这里执行查询，而是让 Agent 在运行时通过工具调用
        return {
            **state_dict,
            "knowledge_query": query,
        }

    async def query_knowledge(
        self,
        query: str,
        mcp_tools: list,
    ) -> Dict[str, Any]:
        """通过 MCP 工具查询知识库。

        参数：
            query: 查询语句
            mcp_tools: MCP 工具列表

        返回：
            查询结果
        """
        # 查找数据库相关工具
        db_tools = [
            tool for tool in mcp_tools
            if any(keyword in tool.name.lower() for keyword in ["sql", "query", "database", "db", "mongo", "postgres", "mysql", "redis"])
        ]

        if not db_tools:
            return {
                "query": query,
                "results": [],
                "error": "没有找到数据库 MCP 工具。请先配置数据库 MCP 服务器。",
            }

        # 返回可用的工具信息，让调用者决定如何使用
        return {
            "query": query,
            "available_tools": [tool.name for tool in db_tools],
            "results": [],
            "message": f"找到 {len(db_tools)} 个数据库工具，请通过工具调用执行查询",
        }


def create_knowledge_agent(model=None) -> KnowledgeAgent:
    """创建知识库 Agent 的工厂函数。

    参数：
        model: 聊天模型实例

    返回：
        KnowledgeAgent 实例
    """
    return KnowledgeAgent(model=model)