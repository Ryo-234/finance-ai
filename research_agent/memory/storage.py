"""Memory 存储抽象层。"""

import abc
import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def utc_now_iso_z() -> str:
    """返回当前 UTC 时间，格式为 ISO-8601，带 'Z' 后缀。"""
    return datetime.now(UTC).isoformat().removesuffix("+00:00") + "Z"


def create_empty_memory() -> dict[str, Any]:
    """创建一个空的记忆结构。"""
    return {
        "version": "1.0",
        "lastUpdated": utc_now_iso_z(),
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


class MemoryStorage(abc.ABC):
    """Memory 存储提供者的抽象基类。"""

    @abc.abstractmethod
    def load(self, user_id: str | None = None) -> dict[str, Any]:
        """加载记忆数据。"""
        pass

    @abc.abstractmethod
    def save(self, memory_data: dict[str, Any], user_id: str | None = None) -> bool:
        """保存记忆数据。"""
        pass


class FileMemoryStorage(MemoryStorage):
    """基于文件的 memory 存储提供者。"""

    def __init__(self, base_dir: str = "./data/memory"):
        """初始化文件 memory 存储。"""
        self.base_dir = Path(base_dir)
        # 缓存：(user_id, memory_data, file_mtime)
        self._cache: dict[str, tuple[dict[str, Any], float | None]] = {}
        self._cache_lock = threading.Lock()

    def _get_memory_file_path(self, user_id: str | None = None) -> Path:
        """获取 memory 文件路径。"""
        if user_id:
            return self.base_dir / f"users" / user_id / "memory.json"
        return self.base_dir / "memory.json"

    def _load_from_file(self, user_id: str | None = None) -> dict[str, Any]:
        """从文件加载记忆。"""
        file_path = self._get_memory_file_path(user_id)

        if not file_path.exists():
            return create_empty_memory()

        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载 memory 文件失败：%s", e)
            return create_empty_memory()

    def load(self, user_id: str | None = None) -> dict[str, Any]:
        """加载记忆数据（带缓存）。"""
        cache_key = user_id or "default"

        try:
            file_path = self._get_memory_file_path(user_id)
            current_mtime = file_path.stat().st_mtime if file_path.exists() else None
        except OSError:
            current_mtime = None

        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None and cached[1] == current_mtime:
                return cached[0]

        memory_data = self._load_from_file(user_id)

        with self._cache_lock:
            self._cache[cache_key] = (memory_data, current_mtime)

        return memory_data

    def save(self, memory_data: dict[str, Any], user_id: str | None = None) -> bool:
        """保存记忆数据到文件。"""
        file_path = self._get_memory_file_path(user_id)
        cache_key = user_id or "default"

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # 添加时间戳
            memory_data = {**memory_data, "lastUpdated": utc_now_iso_z()}

            # 原子写入：先写临时文件，再 rename
            temp_path = file_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)

            temp_path.replace(file_path)

            # 更新缓存
            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                mtime = None

            with self._cache_lock:
                self._cache[cache_key] = (memory_data, mtime)

            logger.info("Memory 已保存到 %s", file_path)
            return True

        except OSError as e:
            logger.error("保存 memory 文件失败：%s", e)
            return False

    # 兼容别名：API 路由使用 load_memory/save_memory 方法名
    def load_memory(self, user_id: str | None = None, agent_name: str | None = None) -> dict[str, Any]:
        """加载记忆数据（load 的别名，兼容 API 路由调用）。"""
        return self.load(user_id=user_id)

    def save_memory(self, memory_data: dict[str, Any], user_id: str | None = None, agent_name: str | None = None) -> bool:
        """保存记忆数据（save 的别名，兼容 API 路由调用）。"""
        return self.save(memory_data, user_id=user_id)


# 全局单例
_storage_instance: Optional[MemoryStorage] = None
_storage_lock = threading.Lock()


def get_memory_storage() -> MemoryStorage:
    """获取 memory 存储实例。"""
    global _storage_instance

    if _storage_instance is not None:
        return _storage_instance

    with _storage_lock:
        if _storage_instance is None:
            _storage_instance = FileMemoryStorage()

        return _storage_instance