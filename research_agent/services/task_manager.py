"""后台任务管理器 —— 全局单例，跟踪所有正在运行的报告生成任务。

设计目标：
- 提交立即返回 task_id（<100ms）
- 后台 asyncio.create_task 跑实际生成
- 进度实时写 DB
- 失败可重试
- 未来可平滑迁移到 Celery/Redis（只改 TaskManager 内部，API 不变）
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from db.database import DatabaseManager
from db.repositories.task_repo import TaskRepo
from db.repositories.cache_repo import CacheRepo
from db.repositories.report_repo import ReportRepo
from billing.quota_manager import QuotaManager

logger = logging.getLogger(__name__)


class TaskManager:
    """全局任务管理器（FastAPI app.state 持有单例）。

    运行中任务用 dict 跟踪，状态变化时同步写 DB（前端轮询 DB）。
    """

    def __init__(self):
        self._running: Dict[str, asyncio.Task] = {}
        self._stats = {"submitted": 0, "completed": 0, "failed": 0}

    def submit(
        self,
        user_id: str,
        topic: str,
        report_type: str,
        thread_id: str = "",
    ) -> str:
        """提交新任务，立即返回 task_id。"""
        # 1. 写 DB（pending）
        db = DatabaseManager.get_instance()
        with db.get_session() as session:
            repo = TaskRepo(session)
            task = repo.create(user_id, topic, report_type, thread_id)

        task_id = task.id

        # 2. 启动后台 asyncio task
        coro = self._run_task(task_id, user_id, topic, report_type, thread_id)
        self._running[task_id] = asyncio.create_task(coro)
        self._stats["submitted"] += 1

        logger.info(f"任务已提交: task_id={task_id}, user={user_id}, topic={topic[:30]}")
        return task_id

    async def _run_task(
        self,
        task_id: str,
        user_id: str,
        topic: str,
        report_type: str,
        thread_id: str,
    ):
        """后台执行：查缓存 → 生成 → 写报告 → 写缓存 → 更新任务状态。"""
        db = DatabaseManager.get_instance()

        try:
            # 0. 缓存检查（在 running 之前查，命中直接 complete）
            with db.get_session() as session:
                cache_repo = CacheRepo(session)
                cached_report = cache_repo.get_cached_report(user_id, topic, report_type)
                if cached_report:
                    # 缓存命中：跳到 completed（进度 100%）
                    with db.get_session() as session:
                        task_repo = TaskRepo(session)
                        task_repo.mark_running(task_id, current_stage="cached")
                        task_repo.update_progress(task_id, 100, "cached")
                        task_repo.mark_completed(task_id, cached_report.id)
                    self._stats["completed"] += 1
                    logger.info(f"任务缓存命中: task_id={task_id} → report={cached_report.id}")
                    return

            # 1. pending → running
            with db.get_session() as session:
                task_repo = TaskRepo(session)
                task_repo.mark_running(task_id, current_stage="planner")
                task_repo.update_progress(task_id, 10, "planner")

            # 2. 调用金融投研流水线（带 progress 回调）
            from graph.research_graph import run_finance_research, _progress_callbacks

            def _on_progress(progress: int, current_stage: str, message: str = ""):
                """阶段进度回调：实时写 DB（前端轮询能看到进度变化）"""
                try:
                    db_local = DatabaseManager.get_instance()
                    with db_local.get_session() as session:
                        TaskRepo(session).update_progress(
                            task_id, progress, current_stage
                        )
                except Exception as e:
                    logger.warning(f"进度更新失败 task={task_id}: {e}")

            # 注册 callback 到 _progress_callbacks（_emit_stage 会查这个 dict）
            tkey = thread_id or f"task-{task_id}"
            _progress_callbacks[tkey] = _on_progress

            try:
                result = await run_finance_research(
                    user_input=topic,
                    thread_id=tkey,
                    report_type=report_type,
                    user_id=user_id,
                    plan_type="pro",  # 任务化后默认 pro（可由用户决定）
                    progress_callback=_on_progress,
                )
            finally:
                # 清理 callback（避免内存泄漏）
                _progress_callbacks.pop(tkey, None)

            # 3. 中途进度更新（每个阶段）
            with db.get_session() as session:
                task_repo = TaskRepo(session)
                task_repo.update_progress(task_id, 90, "report_synthesizer")

            # 4. 保存报告 + 写缓存
            answer = result.get("answer", "")
            sources = result.get("sources", [])

            if not answer or len(answer) < 100:
                raise RuntimeError("报告生成失败：内容为空")

            with db.get_session() as session:
                # 创建报告
                title = self._make_title(topic, report_type)
                report_repo = ReportRepo(session)
                report = report_repo.create(
                    user_id=user_id,
                    title=title,
                    report_type=report_type,
                    topic=topic,
                    thread_id=thread_id or task_id,
                )
                est_tokens = max(1, len(answer) // 2)
                report_repo.update_content(report.id, answer, sources)
                report_repo.update_token_used(report.id, est_tokens)
                if result.get("compliance_checked"):
                    report_repo.update_compliance(report.id, "passed")

                # 写缓存
                cache_repo = CacheRepo(session)
                cache_repo.cache_report(user_id, topic, report_type, report.id, ttl_hours=24)

                # 记录用量
                quota = QuotaManager(session)
                quota.record_report(user_id, report.id)
                quota.record_tokens(user_id, est_tokens, report.id)

                # 标记任务完成（在 with 块内，避免 DetachedInstanceError）
                task_repo = TaskRepo(session)
                report_id_str = report.id
                task_repo.mark_completed(task_id, report_id_str)

            self._stats["completed"] += 1
            logger.info(f"任务完成: task_id={task_id}, report_id={report_id_str}")

        except Exception as e:
            logger.exception(f"任务执行失败: task_id={task_id}, error={e}")
            try:
                with db.get_session() as session:
                    task_repo = TaskRepo(session)
                    task_repo.mark_failed(task_id, str(e)[:2000])
            except Exception:
                pass
            self._stats["failed"] += 1
        finally:
            self._running.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        """取消正在运行的任务。"""
        if task_id in self._running:
            self._running[task_id].cancel()
            return True
        return False

    def retry(self, task_id: str, user_id: str) -> Optional[str]:
        """重试失败任务：reset 状态 + 重新提交。"""
        db = DatabaseManager.get_instance()
        with db.get_session() as session:
            task = TaskRepo(session).get(task_id)
            if not task:
                return None
            if task.status != "failed":
                return None  # 只允许重试 failed 任务

            topic = task.topic
            report_type = task.report_type
            thread_id = task.thread_id

            # 重置状态
            TaskRepo(session).reset_for_retry(task_id)

        # 重新提交
        return self.submit(user_id, topic, report_type, thread_id)

    def get_stats(self) -> dict:
        """获取实时任务统计。"""
        return {
            "running": len(self._running),
            "total_submitted": self._stats["submitted"],
            "total_completed": self._stats["completed"],
            "total_failed": self._stats["failed"],
        }

    @staticmethod
    def _make_title(topic: str, report_type: str) -> str:
        """根据 topic 生成报告标题。"""
        topic = topic.strip()
        if not topic:
            return "研究报告"
        short = topic[:30]
        type_labels = {
            "industry_research": "行业研究",
            "company_deep": "公司深度",
            "macro_brief": "宏观简报",
            "strategy_daily": "策略日报",
        }
        if report_type in type_labels:
            return f"{short} - {type_labels[report_type]}"
        return short


# 全局单例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取任务管理器单例。"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
