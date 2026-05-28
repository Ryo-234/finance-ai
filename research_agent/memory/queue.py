"""Memory 更新队列 - 带防抖机制。"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """待处理记忆更新的对话上下文。"""

    thread_id: str
    messages: list[Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    user_id: str | None = None
    correction_detected: bool = False
    reinforcement_detected: bool = False


class MemoryUpdateQueue:
    """带防抖机制的 memory 更新队列。"""

    def __init__(self, debounce_seconds: float = 30.0):
        """初始化队列。"""
        self.debounce_seconds = debounce_seconds
        self._queue: list[ConversationContext] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._processing = False

    def add(
        self,
        thread_id: str,
        messages: list[Any],
        user_id: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> None:
        """添加对话到更新队列。"""
        with self._lock:
            # 去重：同一 thread_id 合并
            self._queue = [c for c in self._queue if c.thread_id != thread_id]

            context = ConversationContext(
                thread_id=thread_id,
                messages=messages,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
            self._queue.append(context)
            self._reset_timer()

        logger.info("Memory 更新已排队，线程 %s，队列大小：%d", thread_id, len(self._queue))

    def add_nowait(
        self,
        thread_id: str,
        messages: list[Any],
        user_id: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> None:
        """立即处理，忽略防抖延迟。"""
        with self._lock:
            self._queue = [c for c in self._queue if c.thread_id != thread_id]

            context = ConversationContext(
                thread_id=thread_id,
                messages=messages,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
            self._queue.append(context)
            self._schedule_timer(0)

        logger.info("Memory 更新已排队立即处理，线程 %s", thread_id)

    def _reset_timer(self) -> None:
        """重置防抖计时器。"""
        self._schedule_timer(self.debounce_seconds)

    def _schedule_timer(self, delay_seconds: float) -> None:
        """调度队列处理。"""
        if self._timer is not None:
            self._timer.cancel()

        self._timer = threading.Timer(delay_seconds, self._process_queue)
        self._timer.daemon = True
        self._timer.start()

    def _process_queue(self) -> None:
        """处理队列中的所有上下文。"""
        with self._lock:
            if self._processing:
                self._schedule_timer(0)
                return

            if not self._queue:
                return

            self._processing = True
            contexts_to_process = self._queue.copy()
            self._queue.clear()
            self._timer = None

        logger.info("正在处理 %d 个 memory 更新", len(contexts_to_process))

        try:
            from memory.updater import MemoryUpdater

            updater = MemoryUpdater()

            for context in contexts_to_process:
                try:
                    success = updater.update_memory(
                        messages=context.messages,
                        thread_id=context.thread_id,
                        user_id=context.user_id,
                        correction_detected=context.correction_detected,
                        reinforcement_detected=context.reinforcement_detected,
                    )
                    if success:
                        logger.info("线程 %s 的 memory 更新成功", context.thread_id)
                    else:
                        logger.warning("线程 %s 的 memory 更新失败", context.thread_id)
                except Exception as e:
                    logger.error("更新线程 %s 的 memory 时出错：%s", context.thread_id, e)

                if len(contexts_to_process) > 1:
                    time.sleep(0.5)

        finally:
            with self._lock:
                self._processing = False

    def flush(self) -> None:
        """强制立即处理队列。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        self._process_queue()

    def clear(self) -> None:
        """清空队列。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._queue.clear()
            self._processing = False

    @property
    def pending_count(self) -> int:
        """获取待处理更新的数量。"""
        with self._lock:
            return len(self._queue)


# 全局单例
_memory_queue: Optional[MemoryUpdateQueue] = None
_queue_lock = threading.Lock()


def get_memory_queue() -> MemoryUpdateQueue:
    """获取全局 memory 更新队列单例。"""
    global _memory_queue

    with _queue_lock:
        if _memory_queue is None:
            from config.memory import get_memory_config
            config = get_memory_config()
            _memory_queue = MemoryUpdateQueue(debounce_seconds=config.debounce_seconds)

        return _memory_queue