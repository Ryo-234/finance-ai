"""东方财富数据源 —— 行情、公告、研报、财务数据。"""

import logging
from typing import List
import aiohttp
from .base import BaseDataSource, FinanceDoc

logger = logging.getLogger(__name__)


class EastMoneyDataSource(BaseDataSource):
    """东方财富公开 API 数据源。

    支持查询：
    - 股票行情（实时价格、涨跌幅）
    - 公司公告（年报、季报、重大事项）
    - 研报数据（机构研报摘要）
    - 基本财务数据
    """

    def __init__(self, config: dict = None):
        super().__init__("eastmoney", config)
        self.base_url = config.get("base_url", "https://push2.eastmoney.com") if config else "https://push2.eastmoney.com"
        self._session: aiohttp.ClientSession = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.eastmoney.com/",
                }
            )
        return self._session

    async def search(self, query: str, max_results: int = 10) -> List[FinanceDoc]:
        """搜索东方财富数据。"""
        docs = []

        # 并行获取行情和新闻
        try:
            quote_docs = await self._search_quotes(query, max_results // 2)
            docs.extend(quote_docs)
        except Exception as e:
            logger.warning(f"东方财富行情查询失败: {e}")

        try:
            news_docs = await self._search_news(query, max_results // 2)
            docs.extend(news_docs)
        except Exception as e:
            logger.warning(f"东方财富新闻查询失败: {e}")

        return docs[:max_results]

    async def _search_quotes(self, query: str, max_results: int) -> List[FinanceDoc]:
        """查询股票行情。"""
        session = await self._get_session()

        # 尝试直接搜索证券代码
        url = "https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult"
        params = {
            "type": "8193",
            "pageindex": 1,
            "pagesize": max_results,
            "keyword": query,
            "name": "zixun",
        }

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        docs = []
        items = data.get("Data", []) if isinstance(data, dict) else []
        for item in items[:max_results]:
            title = item.get("Title", "") or item.get("Name", "")
            content = item.get("Content", "") or item.get("Summary", "")
            url = item.get("Url", "") or item.get("ContentUrl", "")
            pub_time = item.get("ShowTime", "") or item.get("DateTime", "")

            docs.append(FinanceDoc(
                title=title,
                content=content[:500] if content else "",
                source_url=url,
                source_name="东方财富",
                publish_time=pub_time,
                doc_type="news",
                symbols=[],
                relevance_score=0.7,
            ))

        return docs

    async def _search_news(self, query: str, max_results: int) -> List[FinanceDoc]:
        """搜索东方财富新闻/公告。"""
        session = await self._get_session()

        url = "https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult"
        params = {
            "type": "8196",
            "pageindex": 1,
            "pagesize": max_results,
            "keyword": query,
            "name": "announcement",
        }

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        docs = []
        items = data.get("Data", []) if isinstance(data, dict) else []
        for item in items[:max_results]:
            docs.append(FinanceDoc(
                title=item.get("Title", ""),
                content=item.get("Content", "")[:500] if item.get("Content") else "",
                source_url=item.get("Url", ""),
                source_name="东方财富",
                publish_time=item.get("ShowTime", ""),
                doc_type="announcement",
                symbols=[],
                relevance_score=0.6,
            ))

        return docs

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


class EastMoneyFreeDataSource(EastMoneyDataSource):
    """东方财富免费版数据源（功能受限）。"""

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.name = "eastmoney_free"

    async def search(self, query: str, max_results: int = 10) -> List[FinanceDoc]:
        """免费版限制搜索结果数量。"""
        return await super().search(query, max_results=min(max_results, 5))
