"""报告数据仓库。"""

from typing import List, Optional
from sqlalchemy.orm import Session
from db.models import Report


class ReportRepo:
    """报告 CRUD 操作。"""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: str,
        title: str,
        report_type: str,
        topic: str,
        thread_id: str = "",
    ) -> Report:
        report = Report(
            user_id=user_id,
            title=title,
            report_type=report_type,
            topic=topic,
            thread_id=thread_id,
        )
        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)
        return report

    def get_by_id(self, report_id: str) -> Report | None:
        return self.session.query(Report).filter(Report.id == report_id).first()

    def list_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        report_type: str = None,
    ) -> List[Report]:
        query = self.session.query(Report).filter(Report.user_id == user_id)
        if report_type:
            query = query.filter(Report.report_type == report_type)
        return (
            query
            .order_by(Report.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_content(self, report_id: str, content: str, sources: list = None) -> Report | None:
        report = self.get_by_id(report_id)
        if report:
            report.content = content
            report.status = "completed"
            if sources is not None:
                report.sources = sources
            self.session.commit()
            self.session.refresh(report)
        return report

    def update_status(self, report_id: str, status: str, error_msg: str = None) -> Report | None:
        report = self.get_by_id(report_id)
        if report:
            report.status = status
            self.session.commit()
            self.session.refresh(report)
        return report

    def update_compliance(self, report_id: str, compliance_status: str) -> Report | None:
        report = self.get_by_id(report_id)
        if report:
            report.compliance_status = compliance_status
            self.session.commit()
            self.session.refresh(report)
        return report

    def update_token_used(self, report_id: str, token_count: int) -> Report | None:
        report = self.get_by_id(report_id)
        if report:
            report.token_used = token_count
            self.session.commit()
            self.session.refresh(report)
        return report

    def delete(self, report_id: str) -> bool:
        report = self.get_by_id(report_id)
        if report:
            self.session.delete(report)
            self.session.commit()
            return True
        return False

    def count_by_user(self, user_id: str, since=None) -> int:
        query = self.session.query(Report).filter(Report.user_id == user_id)
        if since:
            query = query.filter(Report.created_at >= since)
        return query.count()
