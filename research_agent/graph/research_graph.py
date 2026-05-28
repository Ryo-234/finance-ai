"""研究流程图 - LangGraph 定义，支持 Checkpointer 和消息序列化。

这个模块是整个研究 Agent 的核心：
1. 定义了研究流程的图结构
2. 支持 Checkpointer 持久化
3. 支持 LangChain 消息序列化
"""

import logging
from typing import Any, Dict, Literal, Optional, Callable
from dataclasses import asdict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, messages_to_dict, messages_from_dict
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, END

from graph.state import ResearchState

logger = logging.getLogger(__name__)


# ============================================================================
# 核心概念解释（通俗版）
# ============================================================================
#
# 什么是 Checkpointer？
#   就像游戏的"存档"功能。你在玩游戏时，可以随时存档。
#   下次打开游戏时，可以从上次存档的地方继续。
#
#   没有 Checkpointer：
#     - 用户问 A → Agent 处理 → 返回答案（Agent 忘了之前的事）
#     - 用户问 B → Agent 重新开始 → 返回答案（不知道 A 的上下文）
#
#   有 Checkpointer：
#     - 用户问 A → Agent 处理 → 存档 → 返回答案
#     - 用户问 B → 读档 → 继续处理 → 存档 → 返回答案
#
# 为什么需要消息序列化？
#   Checkpointer 把状态存到数据库时，只能存"能序列化"的东西。
#   LangChain 的消息对象（HumanMessage, AIMessage）本身不能直接存到 JSON。
#   所以要转换成 dict 存进去，用的时候再转回来。
#
# ============================================================================


# 全局图实例和检查点管理器
_graph: Optional[StateGraph] = None
_checkpointer: Optional[BaseCheckpointSaver] = None
_middleware_manager = None


def set_checkpointer(checkpointer: Optional[BaseCheckpointSaver]) -> None:
    """设置检查点持久化器。

    Args:
        checkpointer: BaseCheckpointSaver 实例
            - InMemorySaver(): 开发用，重启丢失
            - AsyncSqliteSaver: SQLite 数据库
            - AsyncPostgresSaver: PostgreSQL 数据库
    """
    global _checkpointer
    _checkpointer = checkpointer
    logger.info(f"Checkpointer 已设置: {type(checkpointer).__name__ if checkpointer else 'None'}")


def set_middleware_manager(manager) -> None:
    """设置中间件管理器。"""
    global _middleware_manager
    _middleware_manager = manager


def _get_runtime_context(thread_id: str | None, user_id: str | None = None) -> dict:
    """构建运行时上下文。

    Args:
        thread_id: 线程 ID（用于 Checkpointer）
        user_id: 用户 ID

    Returns:
        运行时上下文字典
    """
    context = {}
    if thread_id:
        context["thread_id"] = thread_id
    if user_id:
        context["user_id"] = user_id
    return context


def _state_to_dict(state: Any) -> dict:
    """将 state 转换为 dict（兼容 dataclass 和 dict）。"""
    if isinstance(state, dict):
        return state
    if hasattr(state, '__dataclass_fields__'):
        return asdict(state)
    return {}


def _merge_middleware_result(state: dict, result) -> dict:
    """将 MiddlewareResult 合并到 state。"""
    if result is None:
        return state

    merged = {**state}

    if hasattr(result, 'updates') and result.updates:
        merged = {**merged, **result.updates}

    if hasattr(result, 'messages') and result.messages:
        current_messages = merged.get("messages", [])
        merged["messages"] = list(current_messages) + list(result.messages)

    return merged


def create_research_graph() -> StateGraph:
    """创建研究流程图。

    返回编译好的 StateGraph，可以直接调用或添加 checkpointer。
    """
    global _graph

    if _graph is not None:
        return _graph

    # 创建状态图
    builder = StateGraph(ResearchState)

    # 添加节点
    builder.add_node("planner", _planner_node)
    builder.add_node("search", _search_node)
    builder.add_node("knowledge", _knowledge_node)
    builder.add_node("synthesizer", _synthesizer_node)

    # 设置入口点
    builder.set_entry_point("planner")

    # 添加边（固定顺序）
    builder.add_edge("planner", "search")
    builder.add_edge("search", "knowledge")
    builder.add_edge("knowledge", "synthesizer")
    builder.add_edge("synthesizer", END)

    # 编译
    _graph = builder.compile()

    return _graph


def compile_graph(checkpointer: Optional[BaseCheckpointSaver] = None):
    """编译研究图并可选地添加检查点。

    Args:
        checkpointer: 检查点持久化器
            - None: 不使用持久化
            - InMemorySaver(): 内存存储
            - AsyncSqliteSaver.from_conn_string("..."): SQLite
            - AsyncPostgresSaver.from_conn_string("..."): PostgreSQL

    Returns:
        编译好的图
    """
    builder = StateGraph(ResearchState)

    builder.add_node("planner", _planner_node)
    builder.add_node("search", _search_node)
    builder.add_node("knowledge", _knowledge_node)
    builder.add_node("synthesizer", _synthesizer_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "search")
    builder.add_edge("search", "knowledge")
    builder.add_edge("knowledge", "synthesizer")
    builder.add_edge("synthesizer", END)

    if checkpointer:
        return builder.compile(checkpointer=checkpointer)

    return builder.compile()


# ============================================================================
# 节点实现
# ============================================================================

async def _apply_before_node(node_name: str, state: dict, runtime: dict) -> dict:
    """应用 before_node 中间件。"""
    global _middleware_manager
    if _middleware_manager is None:
        return state

    before_result = await _middleware_manager.apply_before_model(state, runtime)
    if before_result:
        state = _merge_middleware_result(state, before_result)

    return state


async def _apply_after_node(node_name: str, state: dict, runtime: dict) -> dict:
    """应用 after_node 中间件。"""
    global _middleware_manager
    if _middleware_manager is None:
        return state

    after_result = await _middleware_manager.apply_after_model(state, runtime)
    if after_result:
        state = _merge_middleware_result(state, after_result)

    return state


async def _planner_node(state: ResearchState) -> dict:
    """规划节点 - 分析用户问题，制定研究计划。"""
    state_dict = _state_to_dict(state)

    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("planner", state_dict, runtime)

    from tools.registry import get_tool_registry
    registry = get_tool_registry()
    planner = registry.get_agent("planner")

    try:
        result = await planner.ainvoke(state_dict)
        if isinstance(result, dict):
            state_dict = {**state_dict, **result}
        else:
            state_dict = {**state_dict, **(_state_to_dict(result))}
    except Exception as e:
        logger.error(f"Planner 执行失败: {e}")
        user_input = state_dict.get('user_input', '')
        state_dict = {**state_dict, **{
            "tasks": [
                {"id": "task_0", "description": f"搜索: {user_input}", "task_type": "search", "status": "pending"},
                {"id": "task_1", "description": f"综合: {user_input}", "task_type": "synthesize", "status": "pending", "dependencies": ["task_0"]},
            ],
            "current_task_index": 0,
            "error": f"Planner 降级: {str(e)}",
        }}

    state_dict = await _apply_after_node("planner", state_dict, runtime)

    return state_dict


async def _search_node(state: ResearchState) -> dict:
    """搜索节点 - 执行搜索任务。"""
    state_dict = _state_to_dict(state)

    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("search", state_dict, runtime)

    from tools.registry import get_tool_registry
    registry = get_tool_registry()
    search_agent = registry.get_agent("search")

    try:
        if hasattr(state, 'get_next_task'):
            task = state.get_next_task()
        else:
            tasks = state_dict.get("tasks", [])
            current_index = state_dict.get("current_task_index", 0)
            task = tasks[current_index] if current_index < len(tasks) else None

        if task and task.get("task_type") == "search":
            result = await search_agent.ainvoke(state_dict, query=task.get("description"))
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error(f"Search 执行失败: {e}")
        state_dict = {**state_dict, **{
            "search_results": f"搜索暂时不可用: {str(e)}",
            "error": f"Search 失败: {str(e)}",
        }}

    state_dict = await _apply_after_node("search", state_dict, runtime)

    return state_dict


async def _knowledge_node(state: ResearchState) -> dict:
    """知识库节点 - 通过 MCP/数据库查询。"""
    state_dict = _state_to_dict(state)

    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("knowledge", state_dict, runtime)

    from tools.registry import get_tool_registry
    registry = get_tool_registry()
    knowledge_agent = registry.get_agent("knowledge")

    try:
        if hasattr(state, 'get_next_task'):
            task = state.get_next_task()
        else:
            tasks = state_dict.get("tasks", [])
            current_index = state_dict.get("current_task_index", 0)
            task = tasks[current_index] if current_index < len(tasks) else None

        if task and task.get("task_type") == "knowledge":
            result = await knowledge_agent.ainvoke(state_dict, query=task.get("description"))
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error(f"Knowledge 执行失败: {e}")
        state_dict = {**state_dict, **{
            "knowledge_results": f"知识库查询暂时不可用: {str(e)}",
            "error": f"Knowledge 失败: {str(e)}",
        }}

    state_dict = await _apply_after_node("knowledge", state_dict, runtime)

    return state_dict


async def _synthesizer_node(state: ResearchState) -> dict:
    """汇总节点 - 生成最终回答。"""
    state_dict = _state_to_dict(state)

    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("synthesizer", state_dict, runtime)

    from tools.registry import get_tool_registry
    registry = get_tool_registry()
    synthesizer = registry.get_agent("synthesizer")

    try:
        result = await synthesizer.ainvoke(state_dict)
        if isinstance(result, dict):
            state_dict = {**state_dict, **result}
        else:
            state_dict = {**state_dict, **(_state_to_dict(result))}
    except Exception as e:
        logger.error(f"Synthesizer 执行失败: {e}")
        state_dict = {**state_dict, **{
            "final_answer": f"生成回答时出错: {str(e)}",
            "error": f"Synthesizer 失败: {str(e)}",
        }}

    state_dict = await _apply_after_node("synthesizer", state_dict, runtime)

    return state_dict


# ============================================================================
# 对外接口
# ============================================================================

def get_research_graph():
    """获取研究图单例。"""
    global _graph
    if _graph is None:
        _graph = create_research_graph()
    return _graph


async def run_research(
    user_input: str,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> dict:
    """运行研究流程（支持 Checkpointer 持久化）。

    Args:
        user_input: 用户的研究问题
        thread_id: 线程 ID，用于持久化
            - 如果不提供，生成随机 ID
            - 如果提供，从上次存档继续
        user_id: 用户 ID
        checkpointer: 检查点持久化器

    Returns:
        包含最终回答和来源的字典
    """
    global _middleware_manager

    if _middleware_manager is None:
        from middleware.factory import get_default_middleware_manager
        _middleware_manager = get_default_middleware_manager()
        logger.info(f"中间件管理器已初始化，启用 {len(_middleware_manager.list_middlewares())} 个中间件")

    # 获取或编译图
    if checkpointer:
        graph = compile_graph(checkpointer=checkpointer)
    else:
        graph = get_research_graph()

    # 准备初始状态
    initial_state = ResearchState(user_input=user_input)
    state_dict = _state_to_dict(initial_state)

    # 添加 thread_id
    if thread_id:
        state_dict["thread_id"] = thread_id

    runtime = _get_runtime_context(thread_id, user_id)

    # 构建配置（用于 Checkpointer）
    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # 执行图
    if checkpointer:
        # 有持久化，从存档继续或新建
        result = await graph.ainvoke(state_dict, config=config)
    else:
        # 无持久化，直接执行
        result = await graph.ainvoke(state_dict)

    # 应用 after_agent 中间件（用于异步任务如记忆更新）
    if _middleware_manager:
        await _middleware_manager.apply_after_agent(result, runtime)

    return {
        "answer": result.get("final_answer", ""),
        "sources": result.get("sources", []),
        "tasks": result.get("tasks", []),
        "error": result.get("error"),
        "thread_id": thread_id,
    }


# ============================================================================
# 消息序列化工具（供 API 层使用）
# ============================================================================

def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """将 LangChain 消息转换为可序列化的字典。

    用于存储到 Checkpointer 或传输到 API。
    """
    return messages_to_dict(messages)


def deserialize_messages(data: list[dict]) -> list[BaseMessage]:
    """从字典恢复 LangChain 消息。

    Args:
        data: messages_to_dict() 返回的格式

    Returns:
        LangChain 消息对象列表
    """
    if not data:
        return []
    return messages_from_dict(data)
