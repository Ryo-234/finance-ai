"""用量记录数据仓库。"""

from datetime import datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func
from db.models import UsageRecord


class UsageRepo:
    """用量统计操作。"""

    def __init__(self, session: Session):
        self.session = session

    def record(self, user_id: str, record_type: str, amount: int, metadata: dict = None) -> UsageRecord:
        record = UsageRecord(
            user_id=user_id,
            record_type=record_type,
            amount=amount,
            metadata_json=metadata or {},
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_monthly_report_count(self, user_id: str) -> int:
        """获取本月报告生成数量。"""
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(UsageRecord)
            .filter(
                UsageRecord.user_id == user_id,
                UsageRecord.record_type == "report_generated",
                UsageRecord.created_at >= month_start,
            )
            .count()
        )

    def get_monthly_token_sum(self, user_id: str) -> int:
        """获取本月 Token 消耗总量。"""
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = (
            self.session.query(func.sum(UsageRecord.amount))
            .filter(
                UsageRecord.user_id == user_id,
                UsageRecord.record_type == "token_consumed",
                UsageRecord.created_at >= month_start,
            )
            .scalar()
        )
        return result or 0

    def get_daily_stats(self, user_id: str, days: int = 7) -> List[dict]:
        """获取最近 N 天每日用量统计。"""
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days)
        records = (
            self.session.query(UsageRecord)
            .filter(
                UsageRecord.user_id == user_id,
                UsageRecord.created_at >= since,
            )
            .order_by(UsageRecord.created_at.asc())
            .all()
        )

        daily = {}
        for r in records:
            day_key = r.created_at.strftime("%Y-%m-%d")
            if day_key not in daily:
                daily[day_key] = {"reports": 0, "tokens": 0}
            if r.record_type == "report_generated":
                daily[day_key]["reports"] += r.amount
            elif r.record_type == "token_consumed":
                daily[day_key]["tokens"] += r.amount

        return [{"date": k, **v} for k, v in sorted(daily.items())]
