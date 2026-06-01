"""线程管理路由 - 基于 Checkpointer。"""

import uuid
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/threads", tags=["threads"])

# ============================================================================
# 通俗解释：什么是线程管理？
# ============================================================================
#
# 想象一个论坛系统：
# - 每个用户可以开多个帖子（线程）
# - 每个帖子有多个回复（消息）
# - 用户 A 的帖子 和 用户 B 的帖子 是完全独立的
#
# IM 渠道也一样：
# - 用户 A 发消息 → 创建/使用 thread_A
# - 用户 B 发消息 → 创建/使用 thread_B
# - A 和 B 不会混在一起
#
# 线程管理做的就是：
# - 给每个用户的对话分配一个唯一的 ID
# - 记录哪个 ID 对应哪个用户
# - 这样用户发消息时，我们知道该恢复哪个对话
#
# Checkpointer 的作用：
# - 线程 ID = 存档文件名
# - Checkpointer = 存档内容
# - 每次对话结束自动存档
# - 下次发消息自动读档
#
# ============================================================================


class ThreadInfo(BaseModel):
    """线程信息。"""

    thread_id: str = Field(..., description="线程 ID")
    title: str = Field(default="", description="会话标题")
    channel: str = Field(default="api", description="IM 渠道")
    chat_id: str = Field(default="anonymous", description="渠道内用户 ID")
    user_id: str = Field(default="default", description="系统用户 ID")
    created_at: float = Field(default_factory=time.time, description="创建时间戳")
    updated_at: float = Field(default_factory=time.time, description="更新时间戳")
    status: str = Field(default="idle", description="状态: idle/busy")
    message_count: int = Field(default=0, description="消息数量")


class ThreadResponse(BaseModel):
    """线程响应。"""

    thread_id: str
    title: str = ""
    channel: str
    chat_id: str
    created_at: float
    updated_at: float
    status: str
    message_count: int


class ThreadListResponse(BaseModel):
    """线程列表响应。"""

    threads: list[ThreadInfo]
    total: int
    limit: int
    offset: int


# 内存中的线程元数据存储
# 生产环境应该用数据库
_threads_meta: dict[str, ThreadInfo] = {}


def get_thread_meta(thread_id: str) -> Optional[ThreadInfo]:
    """获取线程元数据。"""
    return _threads_meta.get(thread_id)


def create_thread_meta(
    channel: str,
    chat_id: str,
    user_id: Optional[str] = None,
) -> str:
    """创建线程元数据。

    Returns:
        thread_id
    """
    thread_id = str(uuid.uuid4())[:8]

    meta = ThreadInfo(
        thread_id=thread_id,
        channel=channel,
        chat_id=chat_id,
        user_id=user_id or "default",
    )

    _threads_meta[thread_id] = meta
    return thread_id


def update_thread_status(thread_id: str, status: str) -> None:
    """更新线程状态。"""
    if thread_id in _threads_meta:
        _threads_meta[thread_id].status = status
        _threads_meta[thread_id].updated_at = time.time()


def increment_message_count(thread_id: str) -> None:
    """增加消息计数。"""
    if thread_id in _threads_meta:
        _threads_meta[thread_id].message_count += 1
        _threads_meta[thread_id].updated_at = time.time()


# ============================================================================
# API 路由
# ============================================================================

class CreateThreadRequest(BaseModel):
    """创建线程请求体。"""
    channel: str = "api"
    chat_id: str = "anonymous"
    user_id: Optional[str] = None


@router.post("/", response_model=ThreadResponse)
async def create_thread(body: CreateThreadRequest):
    """创建新线程。

    流程：
    1. 生成新的 thread_id
    2. 保存元数据（channel, chat_id 等）
    3. 返回 thread_id 给调用者

    IM 渠道调用时会传入 channel 和 chat_id。
    """
    thread_id = create_thread_meta(body.channel, body.chat_id, body.user_id)
    meta = _threads_meta[thread_id]

    return ThreadResponse(
        thread_id=meta.thread_id,
        channel=meta.channel,
        chat_id=meta.chat_id,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        status=meta.status,
        message_count=meta.message_count,
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str):
    """获取线程信息。"""
    meta = get_thread_meta(thread_id)

    if not meta:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    return ThreadResponse(
        thread_id=meta.thread_id,
        channel=meta.channel,
        chat_id=meta.chat_id,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        status=meta.status,
        message_count=meta.message_count,
    )


@router.get("/", response_model=ThreadListResponse)
async def list_threads(
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出线程。

    可以按 channel 或 user_id 过滤。
    """
    threads = list(_threads_meta.values())

    # 过滤
    if channel:
        threads = [t for t in threads if t.channel == channel]
    if user_id:
        threads = [t for t in threads if t.user_id == user_id]

    # 按更新时间排序
    threads.sort(key=lambda t: t.updated_at, reverse=True)

    # 分页
    total = len(threads)
    threads = threads[offset:offset + limit]

    return ThreadListResponse(
        threads=threads,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    """删除线程。

    注意：这只会删除元数据，不会删除 Checkpointer 中的存档。
    存档会在下次调用时自动覆盖。
    """
    if thread_id not in _threads_meta:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    del _threads_meta[thread_id]

    return {"success": True, "message": f"Thread {thread_id} deleted"}


@router.patch("/{thread_id}/status")
async def update_status(thread_id: str, status: str):
    """更新线程状态。

    状态：
    - idle: 空闲，可接受新请求
    - busy: 处理中，忽略新请求
    """
    meta = get_thread_meta(thread_id)

    if not meta:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    if status not in ("idle", "busy"):
        raise HTTPException(status_code=400, detail="Status must be 'idle' or 'busy'")

    update_thread_status(thread_id, status)

    return {"success": True, "status": status}
