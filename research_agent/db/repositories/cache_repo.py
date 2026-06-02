"""报告缓存数据仓库 —— 高速查询 + 写入。"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from db.models import ReportCache, Report

logger = logging.getLogger(__name__)


def compute_topic_hash(user_id: str, topic: str, report_type: str) -> str:
    """生成缓存 key：user_id + topic + report_type 的 MD5。

    包含 user_id 实现用户级别隔离。
    """
    raw = f"{user_id}:{topic.strip()}:{report_type}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class CacheRepo:
    """报告缓存仓库。"""

    def __init__(self, session: Session):
        self.session = session

    def get_cached_report(
        self, user_id: str, topic: str, report_type: str
    ) -> Optional[Report]:
        """查询缓存：命中返回 Report，未命中返回 None。

        命中条件：
        - topic_hash 匹配
        - expires_at > now()
        - 关联的 Report 仍存在
        """
        topic_hash = compute_topic_hash(user_id, topic, report_type)
        cache = (
            self.session.query(ReportCache)
            .filter(
                ReportCache.user_id == user_id,
                ReportCache.topic_hash == topic_hash,
                ReportCache.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not cache:
            return None

        # 命中统计
        cache.hit_count += 1
        cache.last_hit_at = datetime.now(timezone.utc)
        self.session.commit()

        return self.session.query(Report).filter(Report.id == cache.report_id).first()

    def cache_report(
        self, user_id: str, topic: str, report_type: str, report_id: str, ttl_hours: int = 24
    ) -> ReportCache:
        """写入缓存。"""
        topic_hash = compute_topic_hash(user_id, topic, report_type)
        expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        # 如果已存在同 hash 缓存，覆盖
        existing = (
            self.session.query(ReportCache)
            .filter(ReportCache.user_id == user_id, ReportCache.topic_hash == topic_hash)
            .first()
        )
        if existing:
            existing.report_id = report_id
            existing.expires_at = expires
            existing.topic = topic
            existing.report_type = report_type
            existing.hit_count = 0
            existing.last_hit_at = None
            self.session.commit()
            return existing

        cache = ReportCache(
            user_id=user_id,
            topic_hash=topic_hash,
            topic=topic,
            report_type=report_type,
            report_id=report_id,
            expires_at=expires,
        )
        self.session.add(cache)
        self.session.commit()
        self.session.refresh(cache)
        return cache

    def cleanup_expired(self) -> int:
        """清理过期缓存。返回清理条数。"""
        now = datetime.now(timezone.utc)
        deleted = (
            self.session.query(ReportCache)
            .filter(ReportCache.expires_at < now)
            .delete()
        )
        self.session.commit()
        if deleted:
            logger.info(f"清理过期缓存: {deleted} 条")
        return deleted

    def get_stats(self) -> dict:
        """获取缓存统计（命中率等）。"""
        from sqlalchemy import func
        total = self.session.query(func.count(ReportCache.id)).scalar() or 0
        total_hits = self.session.query(func.sum(ReportCache.hit_count)).scalar() or 0
        return {
            "total_cached": total,
            "total_hits": total_hits,
        }
