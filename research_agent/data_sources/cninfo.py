"""巨潮资讯数据源 —— A 股上市公司公告。"""

import logging
from typing import List
import aiohttp
from .base import BaseDataSource, FinanceDoc

logger = logging.getLogger(__name__)


class CnInfoDataSource(BaseDataSource):
    """巨潮资讯网数据源。

    提供 A 股上市公司公告全文检索，数据最权威但接口有频次限制。
    """

    def __init__(self, config: dict = None):
        super().__init__("cninfo", config)
        self._session: aiohttp.ClientSession = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "http://www.cninfo.com.cn/",
                }
            )
        return self._session

    async def search(self, query: str, max_results: int = 10) -> List[FinanceDoc]:
        """搜索巨潮资讯公告。"""
        session = await self._get_session()
        docs = []

        url = "http://www.cninfo.com.cn/new/fulltextSearch/full"
        params = {
            "searchkey": query,
            "sdate": "",
            "edate": "",
            "isfulltext": "false",
            "sortName": "pubdate",
            "sortType": "desc",
            "pageNum": 1,
            "pageSize": max_results,
        }

        try:
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    docs = self._parse_results(data, max_results)
        except Exception as e:
            logger.warning(f"巨潮资讯搜索失败: {e}")

        return docs

    def _parse_results(self, data: dict, max_results: int) -> List[FinanceDoc]:
        """解析巨潮资讯返回结果。"""
        docs = []
        announcements = data.get("announcements", []) if isinstance(data, dict) else []

        for item in announcements[:max_results]:
            sec_code = item.get("secCode", "")
            sec_name = item.get("secName", "")
            title = item.get("announcementTitle", "")
            pub_time = item.get("announcementTime", "")
            adjunct_url = item.get("adjunctUrl", "")

            # 构建完整 URL
            if adjunct_url and not adjunct_url.startswith("http"):
                adjunct_url = f"https://static.cninfo.com.cn/{adjunct_url}"

            docs.append(FinanceDoc(
                title=f"[{sec_code} {sec_name}] {title}" if sec_code else title,
                content=f"{sec_name} 于 {pub_time} 发布公告：{title}",
                source_url=adjunct_url,
                source_name="巨潮资讯",
                publish_time=pub_time,
                doc_type="announcement",
                symbols=[sec_code] if sec_code else [],
                relevance_score=0.8,
            ))

        return docs

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
