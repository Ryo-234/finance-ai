"""研究流程图 - LangGraph 定义，支持 Checkpointer 和消息序列化。

这个模块是整个研究 Agent 的核心：
1. 定义了研究流程的图结构
2. 支持 Checkpointer 持久化
3. 支持 LangChain 消息序列化
"""

import asyncio
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


# 按线程 ID 索引的流式管道（参考 DeerFlow MemoryStreamBridge 模式）
_streams: dict[str, "asyncio.Queue"] = {}


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
        updates = result.updates
        # 特殊处理 messages 字段：合并而不是覆盖
        if "messages" in updates and "messages" in merged:
            merged["messages"] = list(merged["messages"]) + list(updates["messages"])
            updates = {k: v for k, v in updates.items() if k != "messages"}
        merged = {**merged, **updates}

    if hasattr(result, 'messages') and result.messages:
        current_messages = merged.get("messages", [])
        merged["messages"] = list(current_messages) + list(result.messages)

    return merged


def create_research_graph() -> StateGraph:
    """创建研究流程图。

    返回编译好的 StateGraph，可以直接调用或添加 checkpointer。
    支持意图路由：
    - greeting: 直接返回问候
    - clarification: 返回澄清问题
    - task: 正常执行 planner → search → knowledge → synthesizer
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

    # 添加条件路由（根据意图类型决定后续流程）
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "greeting": END,
            "clarification": END,
            "task": "search",
        }
    )

    # 任务流程：search → knowledge → synthesizer → END（精简，移除 RAG）
    builder.add_edge("search", "knowledge")
    builder.add_edge("knowledge", "synthesizer")
    builder.add_edge("synthesizer", END)

    # 编译
    _graph = builder.compile()

    return _graph


def _route_after_planner(state: ResearchState) -> Literal["greeting", "clarification", "task"]:
    """根据意图类型决定后续路由。

    Args:
        state: 当前状态

    Returns:
        路由目标：greeting / clarification / task
    """
    intent = state.intent if hasattr(state, "intent") else "task"


    # 检查是否需要澄清
    if hasattr(state, "needs_clarification") and state.needs_clarification:
        return "clarification"

    # 检查是否是问候
    if intent == "greeting":
        return "greeting"

    return "task"


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
    builder.add_node("rag", _rag_node)
    builder.add_node("knowledge", _knowledge_node)
    builder.add_node("synthesizer", _synthesizer_node)

    builder.set_entry_point("planner")

    # 添加条件路由
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "greeting": END,
            "clarification": END,
            "task": "search",
        }
    )

    builder.add_edge("search", "rag")
    builder.add_edge("rag", "knowledge")
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
            all_tasks = state.tasks if hasattr(state, 'tasks') else []
            # 在任务列表中查找当前任务的索引
            task_index = next((i for i, t in enumerate(all_tasks) if t is task), -1)
        else:
            all_tasks = state_dict.get("tasks", [])
            task_index = state_dict.get("current_task_index", 0)
            task = all_tasks[task_index] if task_index < len(all_tasks) else None


        if task and task.get("task_type") == "search" and task_index >= 0:
            # 更新任务状态为运行中
            all_tasks[task_index]["status"] = "running"
            state_dict["tasks"] = all_tasks

            result = await search_agent.ainvoke(state_dict, query=task.get("description"))
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}
                sr = state_dict.get("search_results", "")

            # 更新任务状态为已完成
            all_tasks[task_index]["status"] = "completed"
            state_dict["tasks"] = all_tasks
        else:
                pass
    except Exception as e:
        logger.error(f"Search 执行失败: {e}")
        state_dict = {**state_dict, **{
            "search_results": f"搜索暂时不可用: {str(e)}",
            "error": f"Search 失败: {str(e)}",
        }}

    state_dict = await _apply_after_node("search", state_dict, runtime)

    return state_dict


async def _rag_node(state: ResearchState) -> dict:
    """RAG 节点 - 从本地向量知识库检索相关文档。"""
    state_dict = _state_to_dict(state)

    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("rag", state_dict, runtime)

    from tools.registry import get_tool_registry
    registry = get_tool_registry()
    rag_agent = registry.get_agent("rag")

    try:
        result = await rag_agent.ainvoke(state_dict)
        if isinstance(result, dict):
            state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error("RAG 执行失败: %s", e)
        state_dict = {**state_dict, "rag_results": [], "error": f"RAG 失败: {str(e)}"}

    state_dict = await _apply_after_node("rag", state_dict, runtime)
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
            all_tasks = state.tasks if hasattr(state, 'tasks') else []
            # 在任务列表中查找当前任务的索引
            task_index = next((i for i, t in enumerate(all_tasks) if t is task), -1)
        else:
            all_tasks = state_dict.get("tasks", [])
            task_index = state_dict.get("current_task_index", 0)
            task = all_tasks[task_index] if task_index < len(all_tasks) else None

        if task and task.get("task_type") == "knowledge" and task_index >= 0:
            # 更新任务状态为运行中
            all_tasks[task_index]["status"] = "running"
            state_dict["tasks"] = all_tasks

            result = await knowledge_agent.ainvoke(state_dict, query=task.get("description"))
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}

            # 更新任务状态为已完成
            all_tasks[task_index]["status"] = "completed"
            state_dict["tasks"] = all_tasks
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
        # 更新合成任务状态为运行中
        tasks = state_dict.get("tasks", [])
        for i, t in enumerate(tasks):
            if t.get("task_type") in ("synthesize", "synthesizer"):
                tasks[i]["status"] = "running"
                state_dict["tasks"] = tasks
                break

        stream_queue = _streams.get(thread_id or "")

        if stream_queue is not None and hasattr(synthesizer, "ainvoke_stream"):
            # 真流式模式：逐 token 发送到队列
            partial_answer = ""
            async for partial in synthesizer.ainvoke_stream(state_dict):
                chunk = partial.get("partial_answer")
                if chunk:
                    partial_answer += chunk
                    await stream_queue.put(chunk)
                final = partial.get("final_answer")
                if final:
                    partial_answer = final
                    state_dict = {**state_dict, **partial}
            await stream_queue.put(None)  # 流式结束信号
        else:
            # 非流式模式（回退）
            sr = state_dict.get("search_results", "")
            kr = state_dict.get("knowledge_results", "")
            result = await synthesizer.ainvoke(state_dict)
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}
            else:
                state_dict = {**state_dict, **(_state_to_dict(result))}

        # 更新合成任务状态为已完成
        for i, t in enumerate(tasks):
            if t.get("task_type") in ("synthesize", "synthesizer"):
                tasks[i]["status"] = "completed"
                state_dict["tasks"] = tasks
                break
    except Exception as e:
        logger.error(f"Synthesizer 执行失败: {e}")
        state_dict = {**state_dict, **{
            "final_answer": f"生成回答时出错: {str(e)}",
            "error": f"Synthesizer 失败: {str(e)}",
        }}
        # 异常时发送流式结束信号
        if stream_queue is not None:
            await stream_queue.put(None)

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
    files_metadata: Optional[list] = None,
    stream_queue: Optional["asyncio.Queue"] = None,
) -> dict:
    """运行研究流程（支持 Checkpointer 持久化和可选流式输出）。

    Args:
        user_input: 用户的研究问题
        thread_id: 线程 ID，用于持久化
        user_id: 用户 ID
        checkpointer: 检查点持久化器
        stream_queue: 异步队列，用于实时流式输出 token
            - 如果提供，合成阶段会逐 token 向队列发送
            - 发送 None 表示流式结束

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

    # 添加用户消息到 messages 列表（add_messages 会自动合并）
    from langchain_core.messages import HumanMessage
    state_dict["messages"] = [HumanMessage(content=user_input)]

    # 添加 thread_id
    if thread_id:
        state_dict["thread_id"] = thread_id

    # 从线程元数据恢复已有标题（确保 TitleMiddleware 不会重复生成）
    if thread_id:
        try:
            from api.routers.threads import _threads_meta
            meta = _threads_meta.get(thread_id)
            if meta and meta.title:
                state_dict["title"] = meta.title
        except Exception:
            pass

    # 注意：图片路径已在用户消息文本中（由飞书渠道注入）
    # Planner 会自动检测并加载图片

    runtime = _get_runtime_context(thread_id, user_id)

    # 流式模式：按线程 ID 注册队列（参考 DeerFlow MemoryStreamBridge）
    if stream_queue is not None and thread_id:
        _streams[thread_id] = stream_queue

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

    logger.info(f"图执行完成，intent={result.get('intent')}, needs_clarification={result.get('needs_clarification')}")

    # 确保流式管道发送结束信号（防止 SSE 订阅者永久阻塞）
    sq = _streams.pop(thread_id, None) if thread_id else None
    if sq is not None:
        try:
            sq.put_nowait(None)
        except asyncio.QueueFull:
            pass

    # 应用 after_agent 中间件（用于异步任务如记忆更新）
    if _middleware_manager:
        agent_result = await _middleware_manager.apply_after_agent(result, runtime)
        if agent_result.updates:
            result = {**result, **agent_result.updates}

    # 根据意图类型返回不同的响应
    intent = result.get("intent", "task")

    # 问候响应
    if intent == "greeting":
        answer = result.get("greeting_response", "")
        if stream_queue is not None:
            await stream_queue.put(answer)
            await stream_queue.put(None)
        return {
            "answer": answer,
            "intent": "greeting",
            "sources": [],
            "tasks": [],
            "title": result.get("title", ""),
            "error": None,
            "thread_id": thread_id,
        }

    # 澄清响应
    if intent == "clarification" or result.get("needs_clarification", False):
        answer = ""
        if stream_queue is not None:
            await stream_queue.put(None)
        return {
            "answer": answer,
            "intent": "clarification",
            "clarification": {
                "question": result.get("clarification_question", ""),
                "type": result.get("clarification_type", "missing_info"),
                "options": result.get("clarification_options", []),
                "context": result.get("clarification_context", ""),
            },
            "sources": [],
            "tasks": [],
            "title": result.get("title", ""),
            "error": None,
            "thread_id": thread_id,
        }

    # 正常任务响应
    return {
        "answer": result.get("final_answer", ""),
        "intent": "task",
        "sources": result.get("sources", []),
        "tasks": result.get("tasks", []),
        "title": result.get("title", ""),
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


# ============================================================================
# 金融投研图结构（新增）
# ============================================================================

_finance_graph: Optional[StateGraph] = None


def create_finance_graph() -> StateGraph:
    """创建金融投研流程图。

    4 节点流水线：planner → finance_search → finance_knowledge → report_synthesizer → END
    """
    global _finance_graph

    if _finance_graph is not None:
        return _finance_graph

    builder = StateGraph(ResearchState)

    # 注册节点
    builder.add_node("planner", _planner_node)
    builder.add_node("finance_search", _finance_search_node)
    builder.add_node("finance_knowledge", _finance_knowledge_node)
    builder.add_node("report_synthesizer", _report_synthesizer_node)

    builder.set_entry_point("planner")

    # 意图路由
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "greeting": END,
            "clarification": END,
            "task": "finance_search",
        }
    )

    # 金融流水线
    builder.add_edge("finance_search", "finance_knowledge")
    builder.add_edge("finance_knowledge", "report_synthesizer")
    builder.add_edge("report_synthesizer", END)

    _finance_graph = builder.compile()
    logger.info("金融投研图已编译: planner → finance_search → finance_knowledge → report_synthesizer")

    return _finance_graph


async def _finance_search_node(state: ResearchState) -> dict:
    """金融搜索节点 —— 从多个金融数据源获取数据。"""
    state_dict = _state_to_dict(state)
    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("finance_search", state_dict, runtime)

    try:
        from agents.finance_search_agent import FinanceSearchAgent
        agent = FinanceSearchAgent()
        result = await agent.ainvoke(state_dict)
        if isinstance(result, dict):
            state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error(f"金融搜索失败: {e}")
        state_dict["search_results"] = f"金融搜索暂时不可用: {str(e)}"
        state_dict["error"] = str(e)

    state_dict = await _apply_after_node("finance_search", state_dict, runtime)
    return state_dict


async def _finance_knowledge_node(state: ResearchState) -> dict:
    """金融知识整合节点 —— 按报告模板组织数据。"""
    state_dict = _state_to_dict(state)
    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("finance_knowledge", state_dict, runtime)

    try:
        from agents.finance_knowledge_agent import FinanceKnowledgeAgent
        agent = FinanceKnowledgeAgent()
        result = await agent.ainvoke(state_dict)
        if isinstance(result, dict):
            state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error(f"金融知识整合失败: {e}")
        state_dict["knowledge_results"] = state_dict.get("search_results", "")
        state_dict["error"] = str(e)

    state_dict = await _apply_after_node("finance_knowledge", state_dict, runtime)
    return state_dict


async def _report_synthesizer_node(state: ResearchState) -> dict:
    """报告合成节点 —— 按模板生成金融研究报告，注入合规声明。"""
    state_dict = _state_to_dict(state)
    thread_id = state_dict.get("thread_id")
    runtime = _get_runtime_context(thread_id)

    state_dict = await _apply_before_node("report_synthesizer", state_dict, runtime)

    try:
        from agents.report_synthesizer import ReportSynthesizerAgent
        agent = ReportSynthesizerAgent()

        # 流式输出
        stream_queue = _streams.get(thread_id or "")
        if stream_queue is not None:
            async for partial in agent.ainvoke_stream(state_dict):
                chunk = partial.get("partial_answer")
                if chunk:
                    await stream_queue.put(chunk)
                final = partial.get("final_answer")
                if final:
                    state_dict = {**state_dict, "final_answer": final}
            await stream_queue.put(None)
        else:
            result = await agent.ainvoke(state_dict)
            if isinstance(result, dict):
                state_dict = {**state_dict, **result}
    except Exception as e:
        logger.error(f"报告合成失败: {e}")
        state_dict["final_answer"] = f"报告生成失败: {str(e)}"
        state_dict["error"] = str(e)
        stream_queue = _streams.get(thread_id or "")
        if stream_queue is not None:
            await stream_queue.put(None)

    state_dict = await _apply_after_node("report_synthesizer", state_dict, runtime)
    return state_dict


async def run_finance_research(
    user_input: str,
    thread_id: Optional[str] = None,
    report_type: str = "company_deep",
    user_id: str = "",
    plan_type: str = "free",
    stream_queue: Optional["asyncio.Queue"] = None,
) -> dict:
    """运行金融投研流水线。

    Args:
        user_input: 用户的研究课题
        thread_id: 线程 ID
        report_type: 报告类型（industry_research/company_deep/macro_brief/strategy_daily）
        user_id: 用户标识
        plan_type: 订阅方案
        stream_queue: 流式输出队列

    Returns:
        包含 final_answer/sources/compliance_checked 的字典
    """
    global _middleware_manager

    if _middleware_manager is None:
        from middleware.factory import get_default_middleware_manager
        _middleware_manager = get_default_middleware_manager()

    graph = create_finance_graph()

    # 初始状态
    initial_state = {
        "user_input": user_input,
        "thread_id": thread_id or "",
        "report_type": report_type,
        "user_id": user_id,
        "plan_type": plan_type,
        "messages": [HumanMessage(content=user_input)],
    }

    if stream_queue is not None and thread_id:
        _streams[thread_id] = stream_queue

    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # 执行金融图
    result = await graph.ainvoke(initial_state, config=config)

    # 清理流式管道
    sq = _streams.pop(thread_id, None) if thread_id else None
    if sq is not None:
        try:
            sq.put_nowait(None)
        except asyncio.QueueFull:
            pass

    # 应用合规中间件
    if _middleware_manager:
        try:
            from middleware.compliance import compliance_after_agent
            result = await compliance_after_agent(initial_state, result)
        except Exception as e:
            logger.warning(f"合规中间件执行失败: {e}")

    intent = result.get("intent", "task")

    if intent == "greeting":
        return {
            "answer": result.get("greeting_response", ""),
            "intent": "greeting",
            "sources": [],
            "tasks": [],
            "title": "",
            "error": None,
            "thread_id": thread_id,
            "compliance_checked": True,
        }

    if intent == "clarification" or result.get("needs_clarification", False):
        return {
            "answer": "",
            "intent": "clarification",
            "clarification": {
                "question": result.get("clarification_question", ""),
                "type": result.get("clarification_type", "missing_info"),
                "options": result.get("clarification_options", []),
                "context": result.get("clarification_context", ""),
            },
            "sources": [],
            "tasks": [],
            "title": "",
            "error": None,
            "thread_id": thread_id,
            "compliance_checked": True,
        }

    return {
        "answer": result.get("final_answer", ""),
        "intent": "task",
        "sources": result.get("sources", []),
        "tasks": result.get("tasks", []),
        "title": result.get("title", ""),
        "error": result.get("error"),
        "thread_id": thread_id,
        "compliance_checked": result.get("compliance_checked", False),
        "compliance_score": result.get("compliance_score", 0),
    }
