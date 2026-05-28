"""记忆管理路由。"""

import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ============== Pydantic 模型 ==============

class MemoryContextSection(BaseModel):
    """记忆上下文分区。"""
    summary: str = Field(default="", description="摘要内容")
    updated_at: str = Field(default="", description="最后更新时间")


class MemoryUserContext(BaseModel):
    """用户上下文。"""
    work_context: MemoryContextSection = Field(default_factory=MemoryContextSection)
    personal_context: MemoryContextSection = Field(default_factory=MemoryContextSection)
    top_of_mind: MemoryContextSection = Field(default_factory=MemoryContextSection)


class MemoryHistoryContext(BaseModel):
    """历史上下文。"""
    recent_months: MemoryContextSection = Field(default_factory=MemoryContextSection)
    earlier_context: MemoryContextSection = Field(default_factory=MemoryContextSection)
    long_term_background: MemoryContextSection = Field(default_factory=MemoryContextSection)


class MemoryFact(BaseModel):
    """记忆事实。"""
    id: str = Field(..., description="事实唯一标识")
    content: str = Field(..., description="事实内容")
    category: str = Field(default="context", description="分类")
    confidence: float = Field(default=0.5, description="置信度 0-1")
    created_at: str = Field(default="", description="创建时间")
    source: str = Field(default="unknown", description="来源")


class MemoryResponse(BaseModel):
    """记忆响应模型。"""
    version: str = Field(default="1.0")
    last_updated: str = Field(default="")
    user: MemoryUserContext = Field(default_factory=MemoryUserContext)
    history: MemoryHistoryContext = Field(default_factory=MemoryHistoryContext)
    facts: list[MemoryFact] = Field(default_factory=list)


class FactCreateRequest(BaseModel):
    """创建记忆事实请求。"""
    content: str = Field(..., min_length=1, description="事实内容")
    category: str = Field(default="context", description="分类")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")


class FactPatchRequest(BaseModel):
    """更新记忆事实请求。"""
    content: Optional[str] = Field(None, min_length=1, description="事实内容")
    category: Optional[str] = Field(None, description="分类")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="置信度")


# ============== 辅助函数 ==============

def _get_effective_user_id() -> str:
    """获取有效的用户 ID。

    这里简化处理，实际应该从认证上下文获取。
    """
    # 简化：默认使用 "default" 用户
    # 生产环境应该从认证上下文获取
    return "default"


def _format_timestamp(ts: float) -> str:
    """格式化时间戳。"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ============== 路由 ==============

@router.get("/", response_model=MemoryResponse)
async def get_memory():
    """获取当前记忆数据。

    返回用户的完整记忆结构，包括：
    - user: 用户上下文（工作背景、个人偏好等）
    - history: 历史上下文（近期情况、长期背景等）
    - facts: 离散的事实列表
    """
    from memory.storage import FileMemoryStorage

    storage = FileMemoryStorage()
    user_id = _get_effective_user_id()

    try:
        data = storage.load_memory(user_id=user_id, agent_name="research")

        if not data:
            # 返回空记忆
            return MemoryResponse()

        # 转换格式
        user_data = data.get("user", {})
        history_data = data.get("history", {})

        facts_data = data.get("facts", [])

        return MemoryResponse(
            version=data.get("version", "1.0"),
            last_updated=data.get("last_updated", ""),
            user=MemoryUserContext(
                work_context=MemoryContextSection(
                    summary=user_data.get("workContext", {}).get("summary", ""),
                    updated_at=user_data.get("workContext", {}).get("updatedAt", ""),
                ),
                personal_context=MemoryContextSection(
                    summary=user_data.get("personalContext", {}).get("summary", ""),
                    updated_at=user_data.get("personalContext", {}).get("updatedAt", ""),
                ),
                top_of_mind=MemoryContextSection(
                    summary=user_data.get("topOfMind", {}).get("summary", ""),
                    updated_at=user_data.get("topOfMind", {}).get("updatedAt", ""),
                ),
            ),
            history=MemoryHistoryContext(
                recent_months=MemoryHistorySection(
                    summary=history_data.get("recentMonths", {}).get("summary", ""),
                    updated_at=history_data.get("recentMonths", {}).get("updatedAt", ""),
                ),
                earlier_context=MemoryHistorySection(
                    summary=history_data.get("earlierContext", {}).get("summary", ""),
                    updated_at=history_data.get("earlierContext", {}).get("updatedAt", ""),
                ),
                long_term_background=MemoryHistorySection(
                    summary=history_data.get("longTermBackground", {}).get("summary", ""),
                    updated_at=history_data.get("longTermBackground", {}).get("updatedAt", ""),
                ),
            ),
            facts=[
                MemoryFact(
                    id=f.get("id", ""),
                    content=f.get("content", ""),
                    category=f.get("category", "context"),
                    confidence=f.get("confidence", 0.5),
                    created_at=f.get("createdAt", ""),
                    source=f.get("source", "unknown"),
                )
                for f in facts_data
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load memory: {str(e)}")


class MemoryHistorySection(BaseModel):
    """历史上下文分区。"""
    summary: str = Field(default="", description="摘要内容")
    updated_at: str = Field(default="", description="最后更新时间")


@router.post("/facts", response_model=MemoryResponse)
async def create_fact(request: FactCreateRequest):
    """创建记忆事实。

    手动添加一个记忆事实到用户记忆中。
    """
    from memory.storage import FileMemoryStorage

    storage = FileMemoryStorage()
    user_id = _get_effective_user_id()

    try:
        memory_data = storage.load_memory(user_id=user_id, agent_name="research")
        if not memory_data:
            memory_data = {
                "version": "1.0",
                "user": {},
                "history": {},
                "facts": [],
            }

        # 生成新事实 ID
        import uuid
        fact_id = f"fact_{uuid.uuid4().hex[:8]}"

        # 添加新事实
        new_fact = {
            "id": fact_id,
            "content": request.content,
            "category": request.category,
            "confidence": request.confidence,
            "createdAt": _format_timestamp(time.time()),
            "source": "manual",
        }

        memory_data["facts"].append(new_fact)

        # 保存
        storage.save_memory(memory_data, user_id=user_id, agent_name="research")

        # 返回更新后的记忆
        return await get_memory()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create fact: {str(e)}")


@router.delete("/facts/{fact_id}", response_model=MemoryResponse)
async def delete_fact(fact_id: str):
    """删除记忆事实。"""
    from memory.storage import FileMemoryStorage

    storage = FileMemoryStorage()
    user_id = _get_effective_user_id()

    try:
        memory_data = storage.load_memory(user_id=user_id, agent_name="research")
        if not memory_data:
            raise HTTPException(status_code=404, detail="Memory not found")

        # 查找并删除事实
        facts = memory_data.get("facts", [])
        original_count = len(facts)
        memory_data["facts"] = [f for f in facts if f.get("id") != fact_id]

        if len(memory_data["facts"]) == original_count:
            raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found")

        # 保存
        storage.save_memory(memory_data, user_id=user_id, agent_name="research")

        return await get_memory()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete fact: {str(e)}")


@router.patch("/facts/{fact_id}", response_model=MemoryResponse)
async def update_fact(fact_id: str, request: FactPatchRequest):
    """更新记忆事实。"""
    from memory.storage import FileMemoryStorage

    storage = FileMemoryStorage()
    user_id = _get_effective_user_id()

    try:
        memory_data = storage.load_memory(user_id=user_id, agent_name="research")
        if not memory_data:
            raise HTTPException(status_code=404, detail="Memory not found")

        # 查找事实
        facts = memory_data.get("facts", [])
        target_fact = None
        for f in facts:
            if f.get("id") == fact_id:
                target_fact = f
                break

        if not target_fact:
            raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found")

        # 更新字段
        if request.content is not None:
            target_fact["content"] = request.content
        if request.category is not None:
            target_fact["category"] = request.category
        if request.confidence is not None:
            target_fact["confidence"] = request.confidence

        # 保存
        storage.save_memory(memory_data, user_id=user_id, agent_name="research")

        return await get_memory()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update fact: {str(e)}")


@router.delete("/")
async def clear_memory():
    """清空所有记忆数据。"""
    from memory.storage import FileMemoryStorage

    storage = FileMemoryStorage()
    user_id = _get_effective_user_id()

    try:
        # 创建空记忆
        empty_memory = {
            "version": "1.0",
            "user": {},
            "history": {},
            "facts": [],
        }
        storage.save_memory(empty_memory, user_id=user_id, agent_name="research")

        return {"success": True, "message": "Memory cleared"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear memory: {str(e)}")