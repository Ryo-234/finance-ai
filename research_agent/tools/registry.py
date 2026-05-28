"""工具注册表 - 管理所有可用工具和 Agent。"""

import logging
from typing import Dict, Callable, Any, Optional, Type, List
from dataclasses import dataclass

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """工具定义。"""

    name: str
    description: str
    func: Callable
    parameters: Dict[str, Any] = None


@dataclass
class AgentDefinition:
    """Agent 定义。"""

    name: str
    description: str
    agent_class: Type
    config: Dict[str, Any] = None


class ToolRegistry:
    """工具注册表 - 统一管理所有工具和 Agent。

    参考 DeerFlow 的工具系统设计模式。
    """

    def __init__(self):
        """初始化工具注册表。"""
        self._tools: Dict[str, ToolDefinition] = {}
        self._agents: Dict[str, AgentDefinition] = {}
        self._agent_instances: Dict[str, Any] = {}
        self._mcp_tools: List[BaseTool] = []

    # ============ 工具管理 ============
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义。"""
        return self._tools.get(name)

    def list_tools(self) -> list:
        """列出所有已注册的工具。"""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def execute_tool(self, name: str, **kwargs) -> Any:
        """执行工具。"""
        tool = self.get_tool(name)
        if tool is None:
            raise ValueError(f"工具 '{name}' 未注册")
        return tool.func(**kwargs)

    # ============ Agent 管理 ============
    def register_agent(self, agent_def: AgentDefinition) -> None:
        """注册 Agent。"""
        self._agents[agent_def.name] = agent_def

    def get_agent(self, name: str) -> Any:
        """获取 Agent 实例（单例）。"""
        if name in self._agent_instances:
            return self._agent_instances[name]

        agent_def = self._agents.get(name)
        if agent_def is None:
            raise ValueError(f"Agent '{name}' 未注册")

        # 创建实例
        agent_instance = agent_def.agent_class(**(agent_def.config or {}))
        self._agent_instances[name] = agent_instance
        return agent_instance

    def list_agents(self) -> list:
        """列出所有已注册的 Agent。"""
        return [
            {"name": a.name, "description": a.description}
            for a in self._agents.values()
        ]

    def clear_instances(self) -> None:
        """清除所有 Agent 实例（用于测试）。"""
        self._agent_instances.clear()

    # ============ MCP 工具管理 ============
    def set_mcp_tools(self, tools: List[BaseTool]) -> None:
        """设置 MCP 工具列表。

        Args:
            tools: MCP 工具列表
        """
        self._mcp_tools = tools
        logger.info(f"已设置 {len(tools)} 个 MCP 工具")

    def get_mcp_tools(self) -> List[BaseTool]:
        """获取当前注册的 MCP 工具列表。

        Returns:
            MCP 工具列表
        """
        return self._mcp_tools

    def list_mcp_tools(self) -> list:
        """列出所有 MCP 工具的信息。

        Returns:
            MCP 工具信息列表
        """
        return [
            {"name": t.name, "description": t.description or ""}
            for t in self._mcp_tools
        ]

    def get_all_tools(self) -> List[Any]:
        """获取所有可用的工具（包括内置工具和 MCP 工具）。

        Returns:
            所有工具列表
        """
        # 返回内置工具函数 + MCP 工具
        all_tools = []

        # 添加内置工具
        for tool_def in self._tools.values():
            all_tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "func": tool_def.func,
                "type": "builtin"
            })

        # 添加 MCP 工具
        for tool in self._mcp_tools:
            all_tools.append({
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "func": getattr(tool, "func", None),
                "type": "mcp"
            })

        return all_tools


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
        _register_default_agents(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """注册默认工具。"""
    from tools.search import SearchTool

    search_tool = SearchTool()
    registry.register_tool(ToolDefinition(
        name="search",
        description="从网络搜索信息",
        func=search_tool.search,
        parameters=search_tool.parameters,
    ))


def _register_default_agents(registry: ToolRegistry) -> None:
    """注册默认 Agent。"""
    from agents.planner import PlannerAgent
    from agents.search_agent import SearchAgent
    from agents.rag_agent import RagAgent
    from agents.synthesizer import SynthesizerAgent
    from agents.knowledge_agent import KnowledgeAgent

    registry.register_agent(AgentDefinition(
        name="planner",
        description="规划 Agent - 分析问题并拆解任务",
        agent_class=PlannerAgent,
    ))

    registry.register_agent(AgentDefinition(
        name="search",
        description="搜索 Agent - 从网络获取最新信息",
        agent_class=SearchAgent,
        config={"provider": "tavily"},
    ))

    registry.register_agent(AgentDefinition(
        name="rag",
        description="RAG Agent - 从知识库检索信息",
        agent_class=RagAgent,
    ))

    registry.register_agent(AgentDefinition(
        name="knowledge",
        description="知识库 Agent - 通过数据库查询获取信息",
        agent_class=KnowledgeAgent,
    ))

    registry.register_agent(AgentDefinition(
        name="synthesizer",
        description="汇总 Agent - 整合结果生成最终回答",
        agent_class=SynthesizerAgent,
    ))