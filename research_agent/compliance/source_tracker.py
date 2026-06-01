"""来源追踪器 —— 记录每个数据点的原始来源和访问时间。"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class SourceRecord:
    """单条数据来源记录。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""  # 来源名称（如"东方财富"）
    url: str = ""  # 来源 URL
    access_time: str = ""  # 获取时间 ISO 格式
    data_type: str = "web"  # web / api / database
    description: str = ""  # 数据描述

    def __post_init__(self):
        if not self.access_time:
            self.access_time = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "access_time": self.access_time,
            "data_type": self.data_type,
            "description": self.description,
        }

    def to_markdown_ref(self, index: int) -> str:
        """生成 Markdown 格式的引用标注。"""
        return f"[{index}] {self.name} - {self.url}（访问时间：{self.access_time[:10]}）"


class SourceTracker:
    """数据来源追踪器。

    在 Agent 处理过程中收集所有数据来源，最后注入到报告末尾。
    """

    def __init__(self):
        self._sources: Dict[str, SourceRecord] = {}  # key=url, 去重

    def track(
        self,
        name: str,
        url: str = "",
        data_type: str = "web",
        description: str = "",
    ) -> str:
        """记录一个数据来源，返回引用 ID。"""
        key = url or name
        if key and key in self._sources:
            return self._sources[key].id

        record = SourceRecord(
            name=name,
            url=url,
            data_type=data_type,
            description=description,
        )

        if key:
            self._sources[key] = record
        else:
            self._sources[record.id] = record

        return record.id

    def track_docs(self, docs: list):
        """批量记录 FinanceDoc 来源。"""
        for doc in docs:
            if hasattr(doc, "source_name") and hasattr(doc, "source_url"):
                self.track(
                    name=doc.source_name,
                    url=doc.source_url,
                    description=doc.title if hasattr(doc, "title") else "",
                )

    def get_all(self) -> List[SourceRecord]:
        """获取所有来源记录。"""
        return list(self._sources.values())

    def get_markdown_section(self) -> str:
        """生成"数据来源"Markdown 章节。"""
        sources = self.get_all()
        if not sources:
            return ""

        lines = ["## 数据来源\n"]
        for i, src in enumerate(sources, 1):
            lines.append(f"{i}. **{src.name}**：{src.url}（访问时间：{src.access_time[:10]}）")

        return "\n".join(lines)

    def get_inline_refs(self) -> Dict[str, str]:
        """获取内联引用映射 {ref_id: markdown_ref}。"""
        refs = {}
        for i, src in enumerate(self.get_all(), 1):
            refs[src.id] = f"[{i}]"
        return refs

    def clear(self):
        """清空来源记录。"""
        self._sources.clear()
