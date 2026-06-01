"""研究图状态定义 - 支持 LangChain 消息序列化。"""

from typing import Annotated, Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    messages_to_dict,
    messages_from_dict,
)
from langgraph.graph import add_messages
from langgraph.graph import StateGraph


@dataclass
class ResearchState:
    """研究图状态定义。

    支持 LangChain 消息对象的完整序列化。
    """

    # 线程 ID（用于流式管道和 Checkpointer）
    thread_id: str = ""

    # 会话标题（由 TitleMiddleware 在首轮对话后自动生成）
    title: str = ""

    # 用户输入
    user_input: str = ""

    # 意图类型：greeting / task / clarification
    intent: str = "task"

    # 任务列表
    tasks: List[Dict[str, Any]] = field(default_factory=list)

    # 当前任务索引
    current_task_index: int = 0

    # 当前任务
    current_task: Optional[Dict[str, Any]] = None

    # 搜索结果
    search_results: str = ""

    # RAG/知识库结果
    knowledge_results: str = ""

    # 汇总结果
    synthesis_result: str = ""

    # 最终回答
    final_answer: str = ""

    # 记忆上下文
    memory_context: str = ""

    # 消息历史 - 使用 add_messages 注解，支持自动管理和持久化
    messages: Annotated[List[BaseMessage], add_messages] = field(default_factory=list)

    # 规划输出
    planner_output: str = ""

    # 来源信息
    sources: List[Dict[str, Any]] = field(default_factory=list)

    # 错误信息
    error: Optional[str] = None

    # ============ 澄清相关字段 ============
    # 是否需要澄清
    needs_clarification: bool = False

    # 澄清问题
    clarification_question: str = ""

    # 澄清类型：missing_info / ambiguous_requirement / approach_choice / risk_confirmation / suggestion
    clarification_type: str = "missing_info"

    # 澄清选项
    clarification_options: List[str] = field(default_factory=list)

    # 澄清上下文
    clarification_context: str = ""

    # 问候回复（用于 intent=greeting 时）
    greeting_response: str = ""

    # ============ 视觉相关字段 ============
    # 已读取的图片 {path: {base64: str, mime_type: str}}
    viewed_images: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # ============ 金融投研相关字段 ============
    # 报告类型：industry_research / company_deep / macro_brief / strategy_daily
    report_type: str = ""

    # 报告模板名称
    report_template: str = ""

    # 结构化金融数据（各数据源聚合后的结果）
    financial_data: Dict[str, Any] = field(default_factory=dict)

    # 合规检查标记
    compliance_checked: bool = False

    # 用户标识
    user_id: str = ""

    # 订阅方案：free / pro / enterprise
    plan_type: str = "free"

    def get_next_task(self) -> Optional[Dict[str, Any]]:
        """获取下一个待执行的任务。"""
        if self.current_task_index >= len(self.tasks):
            return None
        return self.tasks[self.current_task_index]

    def mark_task_complete(self, task_id: str, result: str) -> None:
        """标记任务完成。"""
        for task in self.tasks:
            if task.get("id") == task_id:
                task["status"] = "completed"
                task["result"] = result
        self.current_task_index += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）。"""
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "user_input": self.user_input,
            "tasks": self.tasks,
            "current_task_index": self.current_task_index,
            "search_results": self.search_results,
            "knowledge_results": self.knowledge_results,
            "final_answer": self.final_answer,
            "messages": self.messages,
            "sources": self.sources,
            "error": self.error,
            "report_type": self.report_type,
            "report_template": self.report_template,
            "financial_data": self.financial_data,
            "compliance_checked": self.compliance_checked,
            "user_id": self.user_id,
            "plan_type": self.plan_type,
        }

    def to_serializable_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典（用于 Checkpointer）。"""
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "user_input": self.user_input,
            "tasks": self.tasks,
            "current_task_index": self.current_task_index,
            "search_results": self.search_results,
            "knowledge_results": self.knowledge_results,
            "final_answer": self.final_answer,
            "messages": messages_to_dict(self.messages),
            "sources": self.sources,
            "error": self.error,
            "report_type": self.report_type,
            "report_template": self.report_template,
            "financial_data": self.financial_data,
            "compliance_checked": self.compliance_checked,
            "user_id": self.user_id,
            "plan_type": self.plan_type,
        }

    @classmethod
    def from_serializable_dict(cls, data: Dict[str, Any]) -> "ResearchState":
        """从可序列化字典恢复状态。"""
        if data is None:
            return cls()

        messages_data = data.get("messages", [])
        # 恢复 LangChain 消息对象
        messages = messages_from_dict(messages_data) if messages_data else []

        return cls(
            thread_id=data.get("thread_id", ""),
            title=data.get("title", ""),
            user_input=data.get("user_input", ""),
            tasks=data.get("tasks", []),
            current_task_index=data.get("current_task_index", 0),
            search_results=data.get("search_results", ""),
            knowledge_results=data.get("knowledge_results", ""),
            final_answer=data.get("final_answer", ""),
            messages=messages,
            sources=data.get("sources", []),
            error=data.get("error"),
            report_type=data.get("report_type", ""),
            report_template=data.get("report_template", ""),
            financial_data=data.get("financial_data", {}),
            compliance_checked=data.get("compliance_checked", False),
            user_id=data.get("user_id", ""),
            plan_type=data.get("plan_type", "free"),
        )


def create_research_state_graph():
    """创建研究状态图。

    返回值可以直接用于 compile(checkpointer=...)。
    """
    builder = StateGraph(ResearchState)

    # 添加节点
    builder.add_node("planner", _planner_node)
    builder.add_node("search", _search_node)
    builder.add_node("knowledge", _knowledge_node)
    builder.add_node("synthesizer", _synthesizer_node)

    # 设置入口点
    builder.set_entry_point("planner")

    # 添加边
    builder.add_edge("planner", "search")
    builder.add_edge("search", "knowledge")
    builder.add_edge("knowledge", "synthesizer")
    builder.add_edge("synthesizer", "__end__")

    return builder


# 节点函数需要导入，在 research_graph.py 中定义
def _planner_node(state: ResearchState) -> Dict[str, Any]:
    """规划节点 - 分析用户问题，制定研究计划。"""
    from agents.planner import PlannerAgent
    from tools.registry import get_tool_registry

    registry = get_tool_registry()
    planner = registry.get_agent("planner")

    try:
        result = planner.ainvoke(state)
        if isinstance(result, dict):
            return result
        return {}
    except Exception as e:
        return {
            "tasks": [
                {"id": "task_0", "description": f"搜索: {state.user_input}", "task_type": "search", "status": "pending"},
                {"id": "task_1", "description": f"综合: {state.user_input}", "task_type": "synthesize", "status": "pending", "dependencies": ["task_0"]},
            ],
            "current_task_index": 0,
            "error": f"Planner 降级: {str(e)}",
        }


def _search_node(state: ResearchState) -> Dict[str, Any]:
    """搜索节点 - 执行搜索任务。"""
    from agents.search_agent import SearchAgent
    from tools.registry import get_tool_registry

    registry = get_tool_registry()
    search_agent = registry.get_agent("search")

    try:
        task = state.get_next_task()
        if task and task.get("task_type") == "search":
            result = search_agent.ainvoke(state, query=task.get("description"))
            if isinstance(result, dict):
                return result
        return {}
    except Exception as e:
        return {"search_results": f"搜索暂时不可用: {str(e)}", "error": f"Search 失败: {str(e)}"}


def _knowledge_node(state: ResearchState) -> Dict[str, Any]:
    """知识库节点 - 通过 MCP/数据库查询。"""
    from agents.knowledge_agent import KnowledgeAgent
    from tools.registry import get_tool_registry

    registry = get_tool_registry()
    knowledge_agent = registry.get_agent("knowledge")

    try:
        task = state.get_next_task()
        if task and task.get("task_type") == "knowledge":
            result = knowledge_agent.ainvoke(state, query=task.get("description"))
            if isinstance(result, dict):
                return result
        return {}
    except Exception as e:
        return {"knowledge_results": f"知识库查询暂时不可用: {str(e)}", "error": f"Knowledge 失败: {str(e)}"}


def _synthesizer_node(state: ResearchState) -> Dict[str, Any]:
    """汇总节点 - 生成最终回答。"""
    from agents.synthesizer import SynthesizerAgent
    from tools.registry import get_tool_registry

    registry = get_tool_registry()
    synthesizer = registry.get_agent("synthesizer")

    try:
        result = synthesizer.ainvoke(state)
        if isinstance(result, dict):
            return result
        return {}
    except Exception as e:
        return {"final_answer": f"生成回答时出错: {str(e)}", "error": f"Synthesizer 失败: {str(e)}"}
