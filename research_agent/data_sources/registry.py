"""数据源注册表 —— 管理和调度多个金融数据源。"""

import asyncio
import logging
from typing import Dict, List, Optional

from .base import BaseDataSource, FinanceDoc

logger = logging.getLogger(__name__)

# 按订阅方案控制数据源访问权限
PLAN_DATA_SOURCE_MAP = {
    "free": ["eastmoney_free"],
    "pro": ["eastmoney_full", "sina_finance"],
    "enterprise": ["eastmoney_full", "sina_finance", "cninfo"],
}


class DataSourceRegistry:
    """金融数据源注册表。

    管理所有已注册的数据源，按订阅方案和报告类型调度查询。
    """

    def __init__(self):
        self._sources: Dict[str, BaseDataSource] = {}

    def register(self, source: BaseDataSource):
        """注册一个数据源。"""
        self._sources[source.name] = source
        logger.info(f"数据源已注册: {source.name}")

    def unregister(self, name: str):
        """注销一个数据源。"""
        if name in self._sources:
            del self._sources[name]
            logger.info(f"数据源已注销: {name}")

    def get(self, name: str) -> Optional[BaseDataSource]:
        """按名称获取数据源。"""
        return self._sources.get(name)

    def list_all(self) -> List[str]:
        """列出所有数据源名称。"""
        return list(self._sources.keys())

    def list_for_plan(self, plan_type: str) -> List[str]:
        """列出某订阅方案可用的数据源名称。"""
        allowed = PLAN_DATA_SOURCE_MAP.get(plan_type, PLAN_DATA_SOURCE_MAP["free"])
        return [name for name in allowed if name in self._sources]

    async def search_all(
        self,
        query: str,
        plan_type: str = "free",
        report_type: str = "",
        max_per_source: int = 5,
    ) -> Dict[str, List[FinanceDoc]]:
        """从所有可用数据源并发搜索。

        参数：
            query: 搜索查询
            plan_type: 用户订阅方案
            report_type: 报告类型
            max_per_source: 每个数据源最大结果数

        返回：
            {source_name: [FinanceDoc, ...]}
        """
        source_names = self.list_for_plan(plan_type)
        results: Dict[str, List[FinanceDoc]] = {}

        for name in source_names:
            source = self._sources[name]
            try:
                # 每个数据源 10s 硬超时（防止单个数据源拖慢整个流程）
                docs = await asyncio.wait_for(
                    source.search(query, max_results=max_per_source),
                    timeout=10.0,
                )
                results[name] = docs
                logger.info(f"数据源 [{name}] 返回 {len(docs)} 条结果，查询: {query[:50]}")
            except asyncio.TimeoutError:
                logger.warning(f"数据源 [{name}] 10s 超时，跳过")
                results[name] = []
            except Exception as e:
                logger.warning(f"数据源 [{name}] 查询失败: {e}")
                results[name] = []

        return results

    async def search_merged(
        self,
        query: str,
        plan_type: str = "free",
        report_type: str = "",
        max_total: int = 15,
    ) -> List[FinanceDoc]:
        """从所有数据源搜索并合并去重结果。"""
        all_results = await self.search_all(
            query, plan_type=plan_type, report_type=report_type
        )

        merged: List[FinanceDoc] = []
        seen_urls: set = set()

        for source_name, docs in all_results.items():
            for doc in docs:
                if doc.source_url and doc.source_url in seen_urls:
                    continue
                if doc.source_url:
                    seen_urls.add(doc.source_url)
                merged.append(doc)

        # 按相关性排序
        merged.sort(key=lambda d: d.relevance_score, reverse=True)
        return merged[:max_total]


# 全局单例
_registry: Optional[DataSourceRegistry] = None


def get_registry() -> DataSourceRegistry:
    """获取数据源注册表单例。"""
    global _registry
    if _registry is None:
        _registry = DataSourceRegistry()
    return _registry
