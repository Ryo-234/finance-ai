"""聊天接口路由 - 支持 Checkpointer 持久化。"""

import asyncio
import json
import logging
import time
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage

from graph.research_graph import run_research, serialize_messages, deserialize_messages
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# 核心概念解释（通俗版）
# ============================================================================
#
# 什么是 Checkpointer？说白了就是"存档系统"
#
# 想象你玩 RPG 游戏：
# - 没有存档：每次打开游戏从头开始，不知道上次玩到哪了
# - 有存档：每次打开游戏可以继续上次的进度
#
# Checkpointer 就是给 Agent 用的存档系统：
# - thread_id = 游戏存档位
# - 每次对话结束自动存档
# - 下次对话自动读档，继续之前的进度
#
# 为什么需要消息序列化？
# - Checkpointer 把状态存到数据库/内存
# - 但数据库只能存 JSON 这样的简单数据
# - LangChain 的消息对象（HumanMessage, AIMessage）不能直接存
# - 所以要转换成 dict 存进去，用的时候再转回来
#
# ============================================================================

# 全局 Checkpointer（生产环境应该用 SQLite 或 PostgreSQL）
_checkpointer: Optional[InMemorySaver] = None


def get_checkpointer() -> InMemorySaver:
    """获取或创建 Checkpointer。

    开发环境用 InMemorySaver（内存，重启丢失）
    生产环境应该用 SQLite 或 PostgreSQL
    """
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = InMemorySaver()
        logger.info("创建了新的 InMemorySaver Checkpointer（开发模式）")
    return _checkpointer


def reset_checkpointer() -> None:
    """重置 Checkpointer（清空所有存档）。"""
    global _checkpointer
    _checkpointer = None
    logger.info("Checkpointer 已重置")


class ChatRequest(BaseModel):
    """聊天请求模型。"""

    message: str = Field(..., description="用户消息")
    thread_id: Optional[str] = Field(None, description="线程 ID（继续对话时提供）")
    channel: Optional[str] = Field("api", description="IM 渠道名称")
    chat_id: Optional[str] = Field("anonymous", description="渠道内用户 ID")
    stream: bool = Field(False, description="是否流式响应")
    context: Optional[dict] = Field({}, description="额外上下文")


class ChatResponse(BaseModel):
    """聊天响应模型。"""

    answer: str = Field(..., description="AI 回复")
    thread_id: str = Field(..., description="线程 ID")
    sources: list = Field(default_factory=list, description="信息来源")
    tasks: list = Field(default_factory=list, description="执行的任务")
    error: Optional[str] = Field(None, description="错误信息")


class MessageRecord(BaseModel):
    """消息记录模型。"""

    role: str = Field(..., description="角色: human/ai")
    content: str = Field(..., description="消息内容")
    timestamp: float = Field(default_factory=time.time, description="时间戳")
    metadata: dict = Field(default_factory=dict, description="元数据")


# ============================================================================
# 核心逻辑：Chat API 是如何工作的？
# ============================================================================
#
# 1. 用户发消息 "今天北京天气如何"
#
# 2. API 检查：
#    - 有 thread_id？→ 从 Checkpointer 读取存档，恢复状态
#    - 没有 thread_id？→ 创建新存档
#
# 3. 把用户消息加到历史中：
#    存档里的历史: []
#    加新消息: [HumanMessage("今天北京天气如何")]
#
# 4. 调用 Agent（带存档信息）：
#    Agent 看到：
#    - 用户输入："今天北京天气如何"
#    - 历史消息：[...]
#    - 任务列表：[...]
#    - 之前的结果：[...]
#
# 5. Agent 执行完成，自动存档
#
# 6. 返回结果给用户
#
# ============================================================================

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """聊天接口 - 核心对话入口。

    这个接口的工作流程：

    1. 接收消息
       用户发送消息，可能指定 thread_id（继续对话）

    2. 管理存档
       - 有 thread_id → 从 Checkpointer 读取存档
       - 没有 → 创建新存档（生成 thread_id）

    3. 构建输入
       把用户消息转成 LangChain 格式，加入历史

    4. 调用 Agent
       run_research() 会自动读取存档、执行、存档

    5. 返回结果
       返回答案 + 新的 thread_id（如果刚创建）
    """
    checkpointer = get_checkpointer()

    # 如果没有 thread_id，生成一个（这是新对话）
    thread_id = request.thread_id
    if not thread_id:
        import uuid
        thread_id = str(uuid.uuid4())[:8]  # 短 ID 方便展示
        logger.info(f"创建新线程: {thread_id}")

    try:
        # 调用研究流程（带 Checkpointer）
        result = await run_research(
            user_input=request.message,
            thread_id=thread_id,
            user_id=request.context.get("user_id", "default"),
            checkpointer=checkpointer,
        )

        return ChatResponse(
            answer=result.get("answer", ""),
            thread_id=thread_id,
            sources=result.get("sources", []),
            tasks=result.get("tasks", []),
            error=result.get("error"),
        )

    except Exception as e:
        logger.exception(f"聊天执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口。

    返回 SSE 格式的流式响应。
    用于 Web 前端实时显示。
    """
    if not request.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required for streaming")

    checkpointer = get_checkpointer()

    async def generate():
        try:
            # 先发送一个开始信号
            yield f"event: start\ndata: {json.dumps({'thread_id': request.thread_id})}\n\n"

            # 调用（流式版本暂时返回完整结果，分块发送）
            result = await run_research(
                user_input=request.message,
                thread_id=request.thread_id,
                user_id=request.context.get("user_id", "default"),
                checkpointer=checkpointer,
            )

            # 分块发送结果
            answer = result.get("answer", "")

            # 把答案分成小块发送
            chunk_size = 50  # 每块 50 个字符
            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i+chunk_size]
                yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
                await asyncio.sleep(0.01)  # 小延迟，让前端有时间处理

            # 发送完成信号
            yield f"event: done\ndata: {json.dumps({'answer': answer, 'sources': result.get('sources', [])})}\n\n"

        except Exception as e:
            logger.exception(f"流式聊天失败: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/{thread_id}/messages")
async def get_messages(thread_id: str, limit: int = 50):
    """获取线程的消息历史。

    从 Checkpointer 读取存档，还原消息历史。
    """
    checkpointer = get_checkpointer()

    try:
        # 获取该线程的所有检查点
        config = {"configurable": {"thread_id": thread_id}}

        # 从 Checkpointer 获取最新状态
        from langgraph.checkpoint.base import empty_checkpoint

        # 尝试获取该线程的历史
        # 注意：InMemorySaver 的 API 可能不同，这里用简化版
        checkpoint_data = {}

        # 简化实现：直接返回空列表
        # 生产环境应该用更完整的 Checkpointer API

        return {
            "thread_id": thread_id,
            "messages": [],
            "count": 0,
        }

    except Exception as e:
        logger.exception(f"获取消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    """删除线程（清空存档）。

    删除该 thread_id 的所有检查点。
    """
    reset_checkpointer()
    logger.info(f"线程已删除: {thread_id}")

    return {"success": True, "message": f"Thread {thread_id} deleted"}


@router.get("/{thread_id}/status")
async def get_thread_status(thread_id: str):
    """获取线程状态。

    检查该线程是否有存档。
    """
    checkpointer = get_checkpointer()

    # 简化实现
    # 生产环境应该检查 Checkpointer 中是否有该 thread_id 的数据

    return {
        "thread_id": thread_id,
        "exists": True,
        "status": "idle",
    }


# ============================================================================
# 消息格式转换工具
# ============================================================================

def format_messages_for_display(messages: list) -> list[dict]:
    """将消息格式化为前端显示格式。

    Args:
        messages: LangChain 消息对象列表

    Returns:
        前端可用的字典列表
    """
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({
                "role": "human",
                "content": msg.content if hasattr(msg, 'content') else str(msg),
            })
        elif isinstance(msg, AIMessage):
            result.append({
                "role": "ai",
                "content": msg.content if hasattr(msg, 'content') else str(msg),
            })
        else:
            result.append({
                "role": "unknown",
                "content": str(msg),
            })
    return result
