"""新浪财经数据源 —— 新闻、行情、基本面。"""

import asyncio
import logging
from typing import List
import aiohttp
from .base import BaseDataSource, FinanceDoc

logger = logging.getLogger(__name__)


class SinaFinanceDataSource(BaseDataSource):
    """新浪财经公开 API 数据源。

    提供财经新闻搜索和行情查询。
    """

    def __init__(self, config: dict = None):
        super().__init__("sina_finance", config)
        self._session: aiohttp.ClientSession = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://finance.sina.com.cn/",
                }
            )
        return self._session

    async def search(self, query: str, max_results: int = 10) -> List[FinanceDoc]:
        """搜索新浪财经新闻。"""
        session = await self._get_session()
        docs = []

        # 新浪财经搜索 API
        url = "https://search.sina.com.cn/finance"
        params = {
            "q": query,
            "range": "all",
            "c": "finance",
            "sort": "time",
            "num": max_results,
        }

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    docs = self._parse_results(text, max_results)
        except Exception as e:
            logger.warning(f"新浪财经搜索失败: {e}")

        return docs

    def _parse_results(self, html: str, max_results: int) -> List[FinanceDoc]:
        """解析新浪财经搜索结果（简单的 HTML 解析）。"""
        import re

        docs = []
        # 匹配搜索结果条目
        # 新浪的搜索结果通常包含标题链接和摘要
        pattern = r'<h2[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?</h2>.*?<p[^>]*>(.*?)</p>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for url, title, summary in matches[:max_results]:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            summary_clean = re.sub(r'<[^>]+>', '', summary).strip()[:300]

            if title_clean:
                docs.append(FinanceDoc(
                    title=title_clean,
                    content=summary_clean,
                    source_url=url,
                    source_name="新浪财经",
                    doc_type="news",
                    relevance_score=0.5,
                ))

        return docs

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
