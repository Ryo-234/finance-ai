"""报告管理 API 路由 —— 生成、查看、删除报告。"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import DatabaseManager, get_db
from db.repositories.report_repo import ReportRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    topic: str
    report_type: str = "company_deep"  # industry_research / company_deep / macro_brief / strategy_daily


class ReportResponse(BaseModel):
    id: str
    user_id: str
    title: str
    report_type: str
    topic: str
    content: str
    sources: list
    status: str
    compliance_status: str
    token_used: int
    created_at: str | None


class ReportListResponse(BaseModel):
    reports: List[ReportResponse]
    total: int


@router.post("/generate", response_model=ReportResponse)
async def generate_report(req: GenerateReportRequest, request: Request):
    """生成金融研究报告（同步端点，集成缓存）。

    - 缓存命中：秒级返回
    - 缓存未命中：跑完整 4 节点流水线（~110 秒）
    """
    user_id = getattr(request.state, "user_id", "default_user")
    plan_type = getattr(request.state, "plan_type", "free")

    db_session = DatabaseManager.get_instance().get_session()
    try:
        # === 第 1 步：缓存检查 ===
        from db.repositories.cache_repo import CacheRepo
        cache_repo = CacheRepo(db_session)
        cached_report = cache_repo.get_cached_report(user_id, req.topic, req.report_type)
        if cached_report:
            logger.info(f"缓存命中: user={user_id}, report={cached_report.id}")
            return ReportResponse(
                id=cached_report.id,
                user_id=cached_report.user_id,
                title=cached_report.title,
                report_type=cached_report.report_type,
                topic=cached_report.topic,
                content=cached_report.content,
                sources=cached_report.sources,
                status=cached_report.status,
                compliance_status=cached_report.compliance_status,
                token_used=cached_report.token_used,
                created_at=cached_report.created_at.isoformat() if cached_report.created_at else None,
            )

        # === 第 2 步：缓存未命中，创建报告 + 跑流水线 ===
        repo = ReportRepo(db_session)
        report = repo.create(
            user_id=user_id,
            title=f"{req.topic[:50]} - {req.report_type}",
            report_type=req.report_type,
            topic=req.topic,
        )

        # 调用金融研究流水线
        from graph.research_graph import run_finance_research

        result = await run_finance_research(
            user_input=req.topic,
            thread_id=request.headers.get("X-Thread-ID", ""),
            report_type=req.report_type,
            user_id=user_id,
            plan_type=plan_type,
        )

        # 更新报告内容
        content = result.get("answer", "")
        sources = result.get("sources", [])
        compliance_checked = result.get("compliance_checked", False)

        repo.update_content(report.id, content, sources)
        repo.update_compliance(
            report.id,
            "passed" if compliance_checked else "failed",
        )

        # === 第 3 步：成功生成 → 写缓存（24h TTL） ===
        try:
            cache_repo.cache_report(
                user_id=user_id,
                topic=req.topic,
                report_type=req.report_type,
                report_id=report.id,
                ttl_hours=24,
            )
            logger.info(f"缓存已写入: report={report.id}")
        except Exception as e:
            logger.warning(f"写缓存失败（不影响返回）: {e}")

        # 刷新数据
        report = repo.get_by_id(report.id)

        return ReportResponse(
            id=report.id,
            user_id=report.user_id,
            title=report.title,
            report_type=report.report_type,
            topic=report.topic,
            content=report.content,
            sources=report.sources,
            status=report.status,
            compliance_status=report.compliance_status,
            token_used=report.token_used,
            created_at=report.created_at.isoformat() if report.created_at else None,
        )
    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"报告生成失败: {str(e)}")
    finally:
        db_session.close()


@router.get("/", response_model=ReportListResponse)
def list_reports(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    report_type: str = None,
):
    """获取报告历史列表。"""
    user_id = getattr(request.state, "user_id", "default_user")

    db_session = DatabaseManager.get_instance().get_session()
    try:
        repo = ReportRepo(db_session)
        reports = repo.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
            report_type=report_type,
        )

        return ReportListResponse(
            reports=[
                ReportResponse(
                    id=r.id,
                    user_id=r.user_id,
                    title=r.title,
                    report_type=r.report_type,
                    topic=r.topic,
                    content=r.content[:200] + "..." if len(r.content) > 200 else r.content,
                    sources=r.sources,
                    status=r.status,
                    compliance_status=r.compliance_status,
                    token_used=r.token_used,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                )
                for r in reports
            ],
            total=len(reports),
        )
    finally:
        db_session.close()


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, request: Request):
    """获取单份报告详情。"""
    db_session = DatabaseManager.get_instance().get_session()
    try:
        repo = ReportRepo(db_session)
        report = repo.get_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        return ReportResponse(
            id=report.id,
            user_id=report.user_id,
            title=report.title,
            report_type=report.report_type,
            topic=report.topic,
            content=report.content,
            sources=report.sources,
            status=report.status,
            compliance_status=report.compliance_status,
            token_used=report.token_used,
            created_at=report.created_at.isoformat() if report.created_at else None,
        )
    finally:
        db_session.close()


# === 异步生成（后台任务化） ===

class AsyncGenerateRequest(BaseModel):
    """异步生成请求。"""
    topic: str
    report_type: str = "company_deep"
    thread_id: str = ""


@router.post("/async-generate")
async def async_generate(req: AsyncGenerateRequest, request: Request, background_tasks: BackgroundTasks):
    """异步生成报告（<100ms 响应，返回 task_id）。

    解决 110 秒长耗时导致的 HTTP 切断问题。
    策略：用独立 daemon 线程跑 _run_task，完全脱离 FastAPI event loop。
    """
    import threading
    import asyncio
    from services.task_manager import get_task_manager
    from db.repositories.task_repo import TaskRepo

    user_id = getattr(request.state, "user_id", "default_user") or "default_user"

    if not req.topic or len(req.topic.strip()) < 2:
        raise HTTPException(status_code=400, detail="课题太短")

    # 1. 立即写 DB（同步）→ 拿到 task_id
    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        task = TaskRepo(session).create(
            user_id=user_id,
            topic=req.topic.strip(),
            report_type=req.report_type,
            thread_id=req.thread_id,
        )
        task_id = task.id

    # 2. 用独立 daemon 线程 + asyncio.run 跑 _run_task
    #    - 完全脱离 FastAPI event loop
    #    - 线程立即返回，不阻塞响应
    manager = get_task_manager()
    def _runner():
        try:
            asyncio.run(manager._run_task(
                task_id=task_id,
                user_id=user_id,
                topic=req.topic.strip(),
                report_type=req.report_type,
                thread_id=req.thread_id,
            ))
        except Exception as e:
            print(f"[TASK THREAD ERROR] task_id={task_id}: {e}")
            import traceback
            traceback.print_exc()

    thread = threading.Thread(target=_runner, daemon=True, name=f"task-{task_id}")
    thread.start()
    manager._running[task_id] = thread
    # 注册 cancel event（让 cancel() 可以设置标志）
    import threading as _th
    manager._cancel_events[task_id] = _th.Event()
    manager._stats["submitted"] += 1

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已提交，可通过 GET /api/tasks/{task_id} 查询进度",
    }


# === 缓存统计 ===

@router.get("/_/cache/stats")
async def cache_stats():
    """缓存统计（命中率 + 数量）。"""
    from db.repositories.cache_repo import CacheRepo
    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        return CacheRepo(session).get_stats()


@router.delete("/{report_id}")
def delete_report(report_id: str, request: Request):
    """删除报告。"""
    db_session = DatabaseManager.get_instance().get_session()
    try:
        repo = ReportRepo(db_session)
        report = repo.get_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        repo.delete(report_id)
        return {"message": "报告已删除", "report_id": report_id}
    finally:
        db_session.close()


@router.get("/{report_id}/export")
def export_report(report_id: str, format: str = "markdown"):
    """导出报告为 Markdown 或 PDF。

    参数：
        format: 导出格式，支持 "markdown"（默认）和 "pdf"

    返回：
        文件下载响应（附件）
    """
    from fastapi.responses import Response
    from services.report_exporter import export_report as do_export

    db_session = DatabaseManager.get_instance().get_session()
    try:
        repo = ReportRepo(db_session)
        report = repo.get_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        if not report.content:
            raise HTTPException(status_code=400, detail="报告内容为空，无法导出")

        try:
            file_bytes, mime_type, filename = do_export(
                report.content, report.title, format=format
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        # 处理中文文件名（RFC 5987 编码）
        from urllib.parse import quote
        ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "report"
        encoded_filename = quote(filename)

        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": (
                    f"attachment; "
                    f'filename="{ascii_fallback}"; '
                    f"filename*=UTF-8''{encoded_filename}"
                ),
                "Content-Length": str(len(file_bytes)),
            },
        )
    finally:
        db_session.close()
