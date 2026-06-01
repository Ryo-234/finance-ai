"""聊天接口路由 - 支持 Checkpointer 持久化。"""

import asyncio
import json
import logging
import time
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage

from graph.research_graph import run_research, serialize_messages, deserialize_messages
from api.routers.threads import _threads_meta
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

# 消息历史缓存：thread_id -> [{"role": "...", "content": "...", "timestamp": ...}, ...]
# 由于 InMemorySaver 的 channel_values 不完整存储所有字段，
# 用此缓存作为消息历史的补充来源
_message_history: dict[str, list[dict]] = {}


def get_checkpointer() -> InMemorySaver:
    """获取或创建 Checkpointer。"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = InMemorySaver()
        logger.info("创建了新的 InMemorySaver Checkpointer（开发模式）")
    return _checkpointer


def _save_message(thread_id: str, role: str, content: str) -> None:
    """将消息保存到历史缓存。"""
    if thread_id not in _message_history:
        _message_history[thread_id] = []
    _message_history[thread_id].append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
    })


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
    title: str = Field(default="", description="会话标题")
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

    # 调用研究流程（带 Checkpointer）
    result = await _do_chat(
        message=request.message,
        thread_id=request.thread_id,
        user_id=request.context.get("user_id", "default"),
        checkpointer=checkpointer,
    )

    return ChatResponse(
        answer=result.get("answer", ""),
        thread_id=result.get("thread_id", ""),
        sources=result.get("sources", []),
        tasks=result.get("tasks", []),
        title=result.get("title", ""),
        error=result.get("error"),
    )


@router.post("/upload", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(..., description="用户消息"),
    thread_id: Optional[str] = Form(None, description="线程 ID"),
    image: UploadFile = File(..., description="图片文件"),
):
    """聊天接口 - 支持图片上传。

    工作流程：
    1. 接收图片并保存到本地
    2. 调用研究流程，图片路径作为上下文传递
    3. 返回结果
    """
    checkpointer = get_checkpointer()

    # 生成 thread_id
    if not thread_id:
        import uuid
        thread_id = str(uuid.uuid4())[:8]
        logger.info(f"创建新线程: {thread_id}")

    # 保存图片到 uploads 目录
    import os
    import uuid as uuid_lib
    from pathlib import Path

    uploads_dir = Path(__file__).parent.parent / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    # 读取图片内容
    image_data = await image.read()
    image_ext = os.path.splitext(image.filename)[1] if image.filename else ".png"
    image_name = f"{uuid_lib.uuid4().hex}{image_ext}"
    image_path = uploads_dir / image_name

    with open(image_path, "wb") as f:
        f.write(image_data)

    logger.info(f"图片已保存: {image_path}")

    # 构建带图片路径的消息
    full_message = f"{message}\n[图片: {image_path}]"

    # 调用研究流程
    result = await _do_chat(
        message=full_message,
        thread_id=thread_id,
        user_id="default",
        checkpointer=checkpointer,
    )

    return ChatResponse(
        answer=result.get("answer", ""),
        thread_id=thread_id,
        sources=result.get("sources", []),
        tasks=result.get("tasks", []),
        title=result.get("title", ""),
        error=result.get("error"),
    )


async def _do_chat(
    message: str,
    thread_id: Optional[str],
    user_id: str,
    checkpointer,
) -> dict:
    """执行聊天逻辑。"""
    import uuid

    # 没有 thread_id 时自动生成
    if not thread_id:
        thread_id = str(uuid.uuid4())[:8]
        logger.info(f"自动生成 thread_id: {thread_id}")

    # 保存用户消息到历史缓存
    _save_message(thread_id, "human", message)

    try:
        result = await run_research(
            user_input=message,
            thread_id=thread_id,
            user_id=user_id,
            checkpointer=checkpointer,
        )
        result["thread_id"] = thread_id

        # 保存 AI 回复到历史缓存
        answer = result.get("answer", "")
        if answer:
            _save_message(thread_id, "ai", answer)

        # 同步标题到线程元数据
        title = result.get("title", "")
        if title and thread_id in _threads_meta:
            _threads_meta[thread_id].title = title

        return result

    except Exception as e:
        logger.exception(f"聊天执行失败: {e}")
        error_msg = str(e)
        _save_message(thread_id, "ai", f"错误: {error_msg}")
        return {"answer": "", "thread_id": thread_id, "error": error_msg}


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口 —— 真正的逐 token 流式输出。

    使用 asyncio.Queue 管道：
    1. 后台运行 run_research，合成阶段逐 token 写入队列
    2. 前端从队列读取，实时以 SSE 推送每个 token
    3. 研究完成后发送 done 事件（含 tasks、sources）
    """
    if not request.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required for streaming")

    checkpointer = get_checkpointer()

    # 保存用户消息到历史缓存
    _save_message(request.thread_id, "human", request.message)

    async def generate():
        stream_queue: asyncio.Queue = asyncio.Queue()

        # 后台任务：运行研究流程，逐 token 写入队列
        async def run_with_stream():
            try:
                result = await run_research(
                    user_input=request.message,
                    thread_id=request.thread_id,
                    user_id=request.context.get("user_id", "default"),
                    checkpointer=checkpointer,
                    stream_queue=stream_queue,
                )
                return result
            except Exception as e:
                logger.exception(f"研究流程执行失败: {e}")
                await stream_queue.put(("error", str(e)))
                return None

        research_task = asyncio.create_task(run_with_stream())

        try:
            # 发送开始信号
            yield f"event: start\ndata: {json.dumps({'thread_id': request.thread_id})}\n\n"

            full_answer = ""

            # 从队列读取 token 并实时推送
            while True:
                item = await stream_queue.get()

                if item is None:
                    # None 表示流式结束
                    break

                if isinstance(item, tuple) and item[0] == "error":
                    # 错误信号
                    yield f"event: error\ndata: {json.dumps({'error': item[1]})}\n\n"
                    return

                # 正常 token
                chunk = item
                full_answer += chunk
                yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"

            # 等待研究任务完成，获取最终结果
            result = await research_task

            if result is None:
                yield f"event: error\ndata: {json.dumps({'error': '研究流程执行失败'})}\n\n"
                return

            answer = result.get("answer", "") or full_answer

            # 保存 AI 回复到历史缓存
            if answer:
                _save_message(request.thread_id, "ai", answer)

            # 同步标题到线程元数据
            title = result.get("title", "")
            if title and request.thread_id in _threads_meta:
                _threads_meta[request.thread_id].title = title

            # 发送完成信号（含完整 answer、sources、tasks、title）
            yield f"event: done\ndata: {json.dumps({'answer': answer, 'sources': result.get('sources', []), 'tasks': result.get('tasks', []), 'title': title})}\n\n"

        except Exception as e:
            logger.exception(f"流式聊天失败: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # 确保后台任务被清理
            if not research_task.done():
                research_task.cancel()

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

    优先使用消息缓存（_message_history），缓存中同时包含人类消息和 AI 回复。
    如果缓存中没有，回退到 Checkpointer 读取存档。
    """
    try:
        # 优先从缓存读取
        if thread_id in _message_history:
            messages = _message_history[thread_id]
            if limit and len(messages) > limit:
                messages = messages[-limit:]
            return {
                "thread_id": thread_id,
                "messages": messages,
                "count": len(messages),
            }

        # 回退：从 Checkpointer 读取
        checkpointer = get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = checkpointer.get_tuple(config)

        if checkpoint_tuple is None:
            return {
                "thread_id": thread_id,
                "messages": [],
                "count": 0,
            }

        checkpoint = checkpoint_tuple.checkpoint
        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])
        final_answer = channel_values.get("final_answer", "")
        greeting_response = channel_values.get("greeting_response", "")

        formatted = format_messages_for_display(messages)

        # 将 AI 回复也加入
        ai_answer = final_answer or greeting_response
        if ai_answer and ai_answer.strip():
            formatted.append({
                "role": "ai",
                "content": ai_answer,
            })

        if limit and len(formatted) > limit:
            formatted = formatted[-limit:]

        # 将回退获取的消息同步到缓存
        _message_history[thread_id] = formatted

        return {
            "thread_id": thread_id,
            "messages": formatted,
            "count": len(formatted),
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
