"""Memory 存储提供者。"""

import abc
import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.agents_config import AGENT_NAME_PATTERN
from deerflow.config.memory_config import get_memory_config
from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)


def utc_now_iso_z() -> str:
    """返回当前 UTC 时间，格式为 ISO-8601，带 'Z' 后缀（与之前的朴素 UTC 输出兼容）。"""
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
    def load(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """加载给定 agent 的记忆数据。"""
        pass

    @abc.abstractmethod
    def reload(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """强制重新加载给定 agent 的记忆数据。"""
        pass

    @abc.abstractmethod
    def save(self, memory_data: dict[str, Any], agent_name: str | None = None, *, user_id: str | None = None) -> bool:
        """保存给定 agent 的记忆数据。"""
        pass


class FileMemoryStorage(MemoryStorage):
    """基于文件的 memory 存储提供者。"""

    def __init__(self):
        """初始化文件 memory 存储。"""
        # 每个用户/agent 的记忆缓存：以 (user_id, agent_name) 元组为 key（None = 全局）
        # 值：(memory_data, file_mtime)
        self._memory_cache: dict[tuple[str | None, str | None], tuple[dict[str, Any], float | None]] = {}
        # 保护所有对 _memory_cache 的并发读写操作
        self._cache_lock = threading.Lock()

    def _validate_agent_name(self, agent_name: str) -> None:
        """验证 agent 名称是否可以安全用于文件系统路径。

        使用代码库中已建立的 AGENT_NAME_PATTERN 来确保一致性，
        并防止路径遍历或其他有问题的字符。
        """
        if not agent_name:
            raise ValueError("Agent 名称必须是非空字符串。")
        if not AGENT_NAME_PATTERN.match(agent_name):
            raise ValueError(f"无效的 agent 名称 {agent_name!r}：名称必须匹配 {AGENT_NAME_PATTERN.pattern}")

    def _get_memory_file_path(self, agent_name: str | None = None, *, user_id: str | None = None) -> Path:
        """获取 memory 文件的路径。"""
        if user_id is not None:
            if agent_name is not None:
                self._validate_agent_name(agent_name)
                return get_paths().user_agent_memory_file(user_id, agent_name)
            config = get_memory_config()
            if config.storage_path and Path(config.storage_path).is_absolute():
                return Path(config.storage_path)
            return get_paths().user_memory_file(user_id)
        # 兼容模式：无 user_id
        if agent_name is not None:
            self._validate_agent_name(agent_name)
            return get_paths().agent_memory_file(agent_name)
        config = get_memory_config()
        if config.storage_path:
            p = Path(config.storage_path)
            return p if p.is_absolute() else get_paths().base_dir / p
        return get_paths().memory_file

    def _load_memory_from_file(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """从文件加载记忆数据。"""
        file_path = self._get_memory_file_path(agent_name, user_id=user_id)

        if not file_path.exists():
            return create_empty_memory()

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载 memory 文件失败：%s", e)
            return create_empty_memory()

    @staticmethod
    def _cache_key(agent_name: str | None = None, *, user_id: str | None = None) -> tuple[str | None, str | None]:
        return (user_id, agent_name)

    def load(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """加载记忆数据（带文件修改时间检查的缓存）。"""
        file_path = self._get_memory_file_path(agent_name, user_id=user_id)
        cache_key = self._cache_key(agent_name, user_id=user_id)

        try:
            current_mtime = file_path.stat().st_mtime if file_path.exists() else None
        except OSError:
            current_mtime = None

        with self._cache_lock:
            cached = self._memory_cache.get(cache_key)
            if cached is not None and cached[1] == current_mtime:
                return cached[0]

        memory_data = self._load_memory_from_file(agent_name, user_id=user_id)

        with self._cache_lock:
            self._memory_cache[cache_key] = (memory_data, current_mtime)

        return memory_data

    def reload(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """重新加载记忆数据，强制使缓存失效。"""
        file_path = self._get_memory_file_path(agent_name, user_id=user_id)
        memory_data = self._load_memory_from_file(agent_name, user_id=user_id)
        cache_key = self._cache_key(agent_name, user_id=user_id)

        try:
            mtime = file_path.stat().st_mtime if file_path.exists() else None
        except OSError:
            mtime = None

        with self._cache_lock:
            self._memory_cache[cache_key] = (memory_data, mtime)
        return memory_data

    def save(self, memory_data: dict[str, Any], agent_name: str | None = None, *, user_id: str | None = None) -> bool:
        """保存记忆数据到文件并更新缓存。"""
        file_path = self._get_memory_file_path(agent_name, user_id=user_id)
        cache_key = self._cache_key(agent_name, user_id=user_id)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # 在添加 lastUpdated 之前进行浅拷贝，这样调用者的 dict 不会作为副作用被修改，
            # 并且在文件写入成功之前缓存引用也不会被静默更新。
            memory_data = {**memory_data, "lastUpdated": utc_now_iso_z()}

            temp_path = file_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)

            temp_path.replace(file_path)

            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                mtime = None

            with self._cache_lock:
                self._memory_cache[cache_key] = (memory_data, mtime)
            logger.info("Memory 已保存到 %s", file_path)
            return True
        except OSError as e:
            logger.error("保存 memory 文件失败：%s", e)
            return False


_storage_instance: MemoryStorage | None = None
_storage_lock = threading.Lock()


def get_memory_storage() -> MemoryStorage:
    """获取已配置的 memory 存储实例。"""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    with _storage_lock:
        if _storage_instance is not None:
            return _storage_instance

        config = get_memory_config()
        storage_class_path = config.storage_class

        try:
            module_path, class_name = storage_class_path.rsplit(".", 1)
            import importlib

            module = importlib.import_module(module_path)
            storage_class = getattr(module, class_name)

            # 验证配置的存储是 MemoryStorage 的实现
            if not isinstance(storage_class, type):
                raise TypeError(f"配置的 memory 存储 '{storage_class_path}' 不是一个类：{storage_class!r}")
            if not issubclass(storage_class, MemoryStorage):
                raise TypeError(f"配置的 memory 存储 '{storage_class_path}' 不是 MemoryStorage 的子类")

            _storage_instance = storage_class()
        except Exception as e:
            logger.error(
                "加载 memory 存储 %s 失败，回退到 FileMemoryStorage：%s",
                storage_class_path,
                e,
            )
            _storage_instance = FileMemoryStorage()

    return _storage_instance