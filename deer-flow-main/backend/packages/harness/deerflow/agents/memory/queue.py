"""带防抖机制的 Memory 更新队列。"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deerflow.config.memory_config import get_memory_config

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """待处理记忆更新的对话上下文。"""

    thread_id: str
    messages: list[Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    agent_name: str | None = None
    user_id: str | None = None
    correction_detected: bool = False
    reinforcement_detected: bool = False


class MemoryUpdateQueue:
    """带防抖机制的 memory 更新队列。

    该队列收集对话上下文，并在可配置的防抖期之后处理。
    防抖窗口内收到的多个对话会被批量处理。
    """

    def __init__(self):
        """初始化 memory 更新队列。"""
        self._queue: list[ConversationContext] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._processing = False

    def add(
        self,
        thread_id: str,
        messages: list[Any],
        agent_name: str | None = None,
        user_id: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> None:
        """将对话添加到更新队列。

        参数：
            thread_id: 线程 ID。
            messages: 对话消息。
            agent_name: 如果提供，记忆按 agent 存储。如果为 None，使用全局记忆。
            user_id: 入队时捕获的用户 ID。存储在 ConversationContext 中，
                因此它可以在 threading.Timer 边界内存活（ContextVar 不会跨原始线程传播）。
            correction_detected: 最近轮次是否包含明确的纠正信号。
            reinforcement_detected: 最近轮次是否包含正向强化信号。
        """
        config = get_memory_config()
        if not config.enabled:
            return

        with self._lock:
            self._enqueue_locked(
                thread_id=thread_id,
                messages=messages,
                agent_name=agent_name,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
            self._reset_timer()

        logger.info("Memory 更新已排队，线程 %s，队列大小：%d", thread_id, len(self._queue))

    def add_nowait(
        self,
        thread_id: str,
        messages: list[Any],
        agent_name: str | None = None,
        user_id: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> None:
        """添加对话并立即在后台开始处理。"""
        config = get_memory_config()
        if not config.enabled:
            return

        with self._lock:
            self._enqueue_locked(
                thread_id=thread_id,
                messages=messages,
                agent_name=agent_name,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
            self._schedule_timer(0)

        logger.info("Memory 更新已排队立即处理，线程 %s，队列大小：%d", thread_id, len(self._queue))

    def _enqueue_locked(
        self,
        *,
        thread_id: str,
        messages: list[Any],
        agent_name: str | None,
        user_id: str | None,
        correction_detected: bool,
        reinforcement_detected: bool,
    ) -> None:
        existing_context = next(
            (context for context in self._queue if context.thread_id == thread_id),
            None,
        )
        merged_correction_detected = correction_detected or (existing_context.correction_detected if existing_context is not None else False)
        merged_reinforcement_detected = reinforcement_detected or (existing_context.reinforcement_detected if existing_context is not None else False)
        context = ConversationContext(
            thread_id=thread_id,
            messages=messages,
            agent_name=agent_name,
            user_id=user_id,
            correction_detected=merged_correction_detected,
            reinforcement_detected=merged_reinforcement_detected,
        )

        self._queue = [c for c in self._queue if c.thread_id != thread_id]
        self._queue.append(context)

    def _reset_timer(self) -> None:
        """重置防抖计时器。"""
        config = get_memory_config()
        self._schedule_timer(config.debounce_seconds)

        logger.debug("Memory 更新计时器已设置为 %ss", config.debounce_seconds)

    def _schedule_timer(self, delay_seconds: float) -> None:
        """在给定延迟后调度队列处理。"""
        # 取消现有的计时器（如果有）
        if self._timer is not None:
            self._timer.cancel()

        self._timer = threading.Timer(
            delay_seconds,
            self._process_queue,
        )
        self._timer.daemon = True
        self._timer.start()

    def _process_queue(self) -> None:
        """处理所有排队的对话上下文。"""
        # 在此处导入以避免循环依赖
        from deerflow.agents.memory.updater import MemoryUpdater

        with self._lock:
            if self._processing:
                # 即使另一个 worker 正在运行，也要保持立即 flush 语义
                self._schedule_timer(0)
                return

            if not self._queue:
                return

            self._processing = True
            contexts_to_process = self._queue.copy()
            self._queue.clear()
            self._timer = None

        logger.info("正在处理 %d 个排队的 memory 更新", len(contexts_to_process))

        try:
            updater = MemoryUpdater()

            for context in contexts_to_process:
                try:
                    logger.info("正在更新线程 %s 的 memory", context.thread_id)
                    success = updater.update_memory(
                        messages=context.messages,
                        thread_id=context.thread_id,
                        agent_name=context.agent_name,
                        correction_detected=context.correction_detected,
                        reinforcement_detected=context.reinforcement_detected,
                        user_id=context.user_id,
                    )
                    if success:
                        logger.info("线程 %s 的 memory 更新成功", context.thread_id)
                    else:
                        logger.warning("线程 %s 的 memory 更新被跳过/失败", context.thread_id)
                except Exception as e:
                    logger.error("更新线程 %s 的 memory 时出错：%s", context.thread_id, e)

                # 在更新之间添加小延迟以避免速率限制
                if len(contexts_to_process) > 1:
                    time.sleep(0.5)

        finally:
            with self._lock:
                self._processing = False

    def flush(self) -> None:
        """强制立即处理队列。

        这对测试或优雅关闭很有用。
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        self._process_queue()

    def flush_nowait(self) -> None:
        """立即在后台线程中开始队列处理。"""
        with self._lock:
            # 守护线程：如果进程在 _process_queue 完成之前退出，
            # 排队的消息可能会丢失。对于尽力的 memory 更新，这是可以接受的。
            self._schedule_timer(0)

    def clear(self) -> None:
        """清除队列而不处理。

        这对测试很有用。
        """
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

    @property
    def is_processing(self) -> bool:
        """检查队列当前是否正在处理。"""
        with self._lock:
            return self._processing


# 全局单例实例
_memory_queue: MemoryUpdateQueue | None = None
_queue_lock = threading.Lock()


def get_memory_queue() -> MemoryUpdateQueue:
    """获取全局 memory 更新队列单例。

    返回：
        memory 更新队列实例。
    """
    global _memory_queue
    with _queue_lock:
        if _memory_queue is None:
            _memory_queue = MemoryUpdateQueue()
        return _memory_queue


def reset_memory_queue() -> None:
    """重置全局 memory 队列。

    这对测试很有用。
    """
    global _memory_queue
    with _queue_lock:
        if _memory_queue is not None:
            _memory_queue.clear()
        _memory_queue = None