"""后台任务 API 路由 —— 异步报告生成的任务管理。"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from db.database import DatabaseManager
from db.repositories.task_repo import TaskRepo
from services.task_manager import get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class SubmitTaskRequest(BaseModel):
    """提交任务请求。"""
    topic: str
    report_type: str = "company_deep"
    thread_id: str = ""


class TaskResponse(BaseModel):
    """任务响应。"""
    id: str
    user_id: str
    thread_id: str
    report_type: str
    topic: str
    status: str
    progress: int
    current_stage: str
    result_report_id: Optional[str] = None
    error_message: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """任务列表响应。"""
    tasks: list
    total: int


def _to_response(task) -> TaskResponse:
    return TaskResponse(**task.to_dict())


@router.post("/submit", response_model=TaskResponse)
async def submit_task(request: SubmitTaskRequest, fastapi_request: Request):
    """提交新任务，立即返回 task_id（<100ms 响应）。"""
    user_id = getattr(fastapi_request.state, "user_id", "default_user") or "default_user"

    if not request.topic or len(request.topic.strip()) < 2:
        raise HTTPException(status_code=400, detail="课题太短")

    manager = get_task_manager()
    task_id = manager.submit(
        user_id=user_id,
        topic=request.topic.strip(),
        report_type=request.report_type,
        thread_id=request.thread_id,
    )

    # 返回新创建的任务对象
    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        task = TaskRepo(session).get(task_id)
        return _to_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request):
    """查询单个任务状态（前端轮询此端点，2 秒一次）。"""
    user_id = getattr(request.state, "user_id", "default_user") or "default_user"

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        task = TaskRepo(session).get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.user_id != user_id:
            # 安全：不能查别人的任务
            raise HTTPException(status_code=403, detail="无权访问此任务")
        return _to_response(task)


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    request: Request,
    limit: int = 20,
    status: Optional[str] = None,
):
    """列出当前用户所有任务（分页 + 状态过滤）。"""
    user_id = getattr(request.state, "user_id", "default_user") or "default_user"

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        tasks = TaskRepo(session).list_by_user(user_id, limit=limit, status=status)
        return TaskListResponse(
            tasks=[_to_response(t).model_dump() for t in tasks],
            total=len(tasks),
        )


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: str, request: Request):
    """重试失败任务。"""
    user_id = getattr(request.state, "user_id", "default_user") or "default_user"

    manager = get_task_manager()
    new_task_id = manager.retry(task_id, user_id)
    if not new_task_id:
        raise HTTPException(status_code=400, detail="任务不可重试（不存在或非 failed 状态）")

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        task = TaskRepo(session).get(new_task_id)
        return _to_response(task)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request):
    """取消正在运行的任务。"""
    user_id = getattr(request.state, "user_id", "default_user") or "default_user"

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        task = TaskRepo(session).get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问此任务")

    manager = get_task_manager()
    success = manager.cancel(task_id)
    return {"task_id": task_id, "cancelled": success}


@router.get("/_/stats")
async def get_task_stats():
    """任务统计（仅供调试用）。"""
    manager = get_task_manager()
    return manager.get_stats()
