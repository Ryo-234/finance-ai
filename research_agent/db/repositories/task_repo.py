"""后台任务数据仓库。"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from db.models import Task

logger = logging.getLogger(__name__)


class TaskRepo:
    """后台任务仓库 —— 增删改查 + 状态转换。"""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: str,
        topic: str,
        report_type: str,
        thread_id: str = "",
    ) -> Task:
        """创建 pending 任务。"""
        task = Task(
            user_id=user_id,
            topic=topic,
            report_type=report_type,
            thread_id=thread_id,
            status="pending",
            progress=0,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self.session.query(Task).filter(Task.id == task_id).first()

    def list_by_user(
        self, user_id: str, limit: int = 20, status: str = None
    ) -> List[Task]:
        """列出用户任务。"""
        query = self.session.query(Task).filter(Task.user_id == user_id)
        if status:
            query = query.filter(Task.status == status)
        return (
            query.order_by(Task.created_at.desc()).limit(limit).all()
        )

    def mark_running(self, task_id: str, current_stage: str = "") -> Optional[Task]:
        """pending → running。"""
        task = self.get(task_id)
        if task:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            task.current_stage = current_stage
            task.progress = 5  # 开始就算 5%
            self.session.commit()
            self.session.refresh(task)
        return task

    def update_progress(
        self, task_id: str, progress: int, current_stage: str = ""
    ) -> Optional[Task]:
        """更新进度和当前阶段。"""
        task = self.get(task_id)
        if task:
            task.progress = max(0, min(100, progress))
            if current_stage:
                task.current_stage = current_stage
            self.session.commit()
            # 注意：不 refresh 避免覆盖其它字段
        return task

    def mark_completed(self, task_id: str, report_id: str) -> Optional[Task]:
        """running → completed。"""
        task = self.get(task_id)
        if task:
            task.status = "completed"
            task.progress = 100
            task.result_report_id = report_id
            task.completed_at = datetime.now(timezone.utc)
            self.session.commit()
            self.session.refresh(task)
        return task

    def mark_failed(self, task_id: str, error_message: str) -> Optional[Task]:
        """任何状态 → failed。"""
        task = self.get(task_id)
        if task:
            task.status = "failed"
            task.error_message = error_message[:2000]
            task.completed_at = datetime.now(timezone.utc)
            self.session.commit()
            self.session.refresh(task)
        return task

    def reset_for_retry(self, task_id: str) -> Optional[Task]:
        """failed → pending（重试用）。"""
        task = self.get(task_id)
        if task and task.status == "failed":
            task.status = "pending"
            task.progress = 0
            task.current_stage = ""
            task.error_message = ""
            task.started_at = None
            task.completed_at = None
            self.session.commit()
            self.session.refresh(task)
        return task
