"""金融数据源抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FinanceDoc:
    """金融文档/数据条目。"""

    title: str
    content: str
    source_url: str
    source_name: str
    publish_time: str = ""  # ISO 格式时间字符串
    doc_type: str = "news"  # news / announcement / financial_data / research
    symbols: List[str] = field(default_factory=list)  # 关联证券代码
    relevance_score: float = 0.0  # 相关性评分 0-1

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "publish_time": self.publish_time,
            "doc_type": self.doc_type,
            "symbols": self.symbols,
            "relevance_score": self.relevance_score,
        }


class BaseDataSource(ABC):
    """金融数据源抽象基类。

    所有金融数据源必须实现 search 方法，返回 FinanceDoc 列表。
    """

    def __init__(self, name: str, config: dict = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[FinanceDoc]:
        """搜索金融数据。

        参数：
            query: 搜索查询字符串
            max_results: 最大返回结果数

        返回：
            FinanceDoc 列表
        """
        ...

    async def health_check(self) -> bool:
        """检查数据源是否可用。"""
        try:
            results = await self.search("test", max_results=1)
            return True
        except Exception:
            return False
