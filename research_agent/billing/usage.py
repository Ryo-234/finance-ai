"""用量追踪器 —— 实时统计和聚合用量数据。"""

from datetime import datetime, timezone
from typing import Dict, List
from collections import defaultdict


class UsageTracker:
    """内存中的用量追踪器（实时统计，定期同步到数据库）。"""

    def __init__(self):
        # {user_id: {date_str: {"reports": 0, "tokens": 0}}}
        self._daily: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"reports": 0, "tokens": 0})
        )

    def track_report(self, user_id: str):
        """记录一次报告生成。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily[user_id][today]["reports"] += 1

    def track_tokens(self, user_id: str, count: int):
        """记录 Token 消耗。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily[user_id][today]["tokens"] += count

    def get_user_stats(self, user_id: str) -> dict:
        """获取某用户的用量统计。"""
        user_data = self._daily.get(user_id, {})
        total_reports = sum(d["reports"] for d in user_data.values())
        total_tokens = sum(d["tokens"] for d in user_data.values())

        return {
            "total_reports": total_reports,
            "total_tokens": total_tokens,
            "daily": [
                {"date": date, "reports": data["reports"], "tokens": data["tokens"]}
                for date, data in sorted(user_data.items())
            ],
        }

    def get_today_stats(self, user_id: str) -> dict:
        """获取今日用量。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_data = self._daily.get(user_id, {}).get(today, {"reports": 0, "tokens": 0})
        return {"date": today, **today_data}

    def clear_user(self, user_id: str):
        """清除某用户的用量数据。"""
        if user_id in self._daily:
            del self._daily[user_id]
