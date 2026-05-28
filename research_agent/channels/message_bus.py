"""消息总线 - 实现发布/订阅模式解耦通道和 Agent。"""

import asyncio
import logging
from typing import Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """消息类型枚举。"""
    INBOUND = "inbound"       # 来自 IM 渠道的消息
    OUTBOUND = "outbound"     # 发往 IM 渠道的消息
    SYSTEM = "system"         # 系统消息


@dataclass
class InboundMessage:
    """入站消息 - 从 IM 渠道收到的用户消息。"""
    channel_name: str                    # 来自哪个渠道（如 "feishu"）
    chat_id: str                          # 渠道内的会话 ID
    user_id: str                          # 发送用户 ID
    text: str                             # 消息文本
    thread_ts: Optional[str] = None       # 用于线程/回复追踪
    files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    message_type: MessageType = MessageType.INBOUND

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "channel_name": self.channel_name,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "text": self.text,
            "thread_ts": self.thread_ts,
            "files": self.files,
            "metadata": self.metadata,
            "message_type": self.message_type.value,
        }


@dataclass
class OutboundMessage:
    """出站消息 - 发往 IM 渠道的消息。"""
    channel_name: str                     # 发往哪个渠道
    chat_id: str                          # 渠道内的会话 ID
    text: str                             # 消息文本
    thread_ts: Optional[str] = None       # 用于线程/回复追踪
    files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    message_type: MessageType = MessageType.OUTBOUND

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "channel_name": self.channel_name,
            "chat_id": self.chat_id,
            "text": self.text,
            "thread_ts": self.thread_ts,
            "files": self.files,
            "metadata": self.metadata,
            "message_type": self.message_type.value,
        }


class MessageBus:
    """消息总线 - 实现发布/订阅模式。

    通俗理解：
    - MessageBus = 邮局
    - Channel = 寄信人/收信人
    - InboundMessage = 收到的信
    - OutboundMessage = 要寄出的信
    - subscribe = 订阅 = 告诉邮局"我的信送到这个地址"
    - publish = 发布 = 把信交给邮局

    工作流程：
    1. Feishu 收到用户消息 → 发布到总线
    2. Agent 订阅了消息 → 收到通知，处理消息
    3. Agent 生成回复 → 发布到总线
    4. Feishu 订阅了回复 → 收到通知，发送消息
    """

    def __init__(self) -> None:
        """初始化消息总线。"""
        # 订阅处理器：channel_name -> [callback列表]
        self._inbound_handlers: dict[str, list] = defaultdict(list)
        self._outbound_handlers: dict[str, list] = defaultdict(list)

        # 全局处理器（处理所有消息）
        self._global_inbound_handlers: list = []
        self._global_outbound_handlers: list = []

        # 订阅队列：用于异步消息处理
        self._inbound_queue: asyncio.Queue = asyncio.Queue()
        self._outbound_queue: asyncio.Queue = asyncio.Queue()

        # 统计信息
        self._stats = {
            "inbound_count": 0,
            "outbound_count": 0,
            "error_count": 0,
        }

        # 运行状态
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        """是否正在运行。"""
        return self._running

    # =========================================================================
    # 订阅管理
    # =========================================================================

    def subscribe_inbound(
        self,
        channel_name: str,
        handler: callable,
    ) -> None:
        """订阅入站消息（来自 IM 的消息）。

        Args:
            channel_name: 渠道名称（如 "feishu"），"*" 表示所有渠道
            handler: 回调函数，签名：async def handler(msg: InboundMessage)
        """
        if channel_name == "*":
            self._global_inbound_handlers.append(handler)
            logger.info(f"已订阅全局入站消息")
        else:
            self._inbound_handlers[channel_name].append(handler)
            logger.info(f"已订阅渠道入站消息: {channel_name}")

    def subscribe_outbound(
        self,
        channel_name: str,
        handler: callable,
    ) -> None:
        """订阅出站消息（发往 IM 的消息）。

        Args:
            channel_name: 渠道名称，"*" 表示所有渠道
            handler: 回调函数，签名：async def handler(msg: OutboundMessage)
        """
        if channel_name == "*":
            self._global_outbound_handlers.append(handler)
            logger.info(f"已订阅全局出站消息")
        else:
            self._outbound_handlers[channel_name].append(handler)
            logger.info(f"已订阅渠道出站消息: {channel_name}")

    def unsubscribe_inbound(
        self,
        channel_name: str,
        handler: callable,
    ) -> None:
        """取消订阅入站消息。"""
        if channel_name == "*":
            if handler in self._global_inbound_handlers:
                self._global_inbound_handlers.remove(handler)
        else:
            if handler in self._inbound_handlers[channel_name]:
                self._inbound_handlers[channel_name].remove(handler)

    def unsubscribe_outbound(
        self,
        channel_name: str,
        handler: callable,
    ) -> None:
        """取消订阅出站消息。"""
        if channel_name == "*":
            if handler in self._global_outbound_handlers:
                self._global_outbound_handlers.remove(handler)
        else:
            if handler in self._outbound_handlers[channel_name]:
                self._outbound_handlers[channel_name].remove(handler)

    # =========================================================================
    # 发布消息
    # =========================================================================

    async def publish_inbound(self, message: InboundMessage) -> None:
        """发布入站消息。

        当 Channel 收到用户消息时调用这个。

        Args:
            message: 入站消息
        """
        self._stats["inbound_count"] += 1
        await self._inbound_queue.put(message)
        logger.debug(f"入站消息已加入队列: {message.channel_name}/{message.chat_id}")

    async def publish_outbound(self, message: OutboundMessage) -> None:
        """发布出站消息。

        当 Agent 要发送消息时调用这个。

        Args:
            message: 出站消息
        """
        self._stats["outbound_count"] += 1
        await self._outbound_queue.put(message)
        logger.debug(f"出站消息已加入队列: {message.channel_name}/{message.chat_id}")

    # =========================================================================
    # 异步消息处理
    # =========================================================================

    async def start(self) -> None:
        """启动消息总线（开始异步处理消息）。"""
        if self._running:
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._process_messages())
        logger.info("消息总线已启动")

    async def stop(self) -> None:
        """停止消息总线。"""
        if not self._running:
            return

        self._running = False

        # 取消处理任务
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        # 清空队列
        while not self._inbound_queue.empty():
            try:
                self._inbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        while not self._outbound_queue.empty():
            try:
                self._outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        logger.info("消息总线已停止")

    async def _process_messages(self) -> None:
        """异步处理消息队列。"""
        while self._running:
            try:
                # 并行处理入站和出站队列
                tasks = []

                # 处理入站消息
                if not self._inbound_queue.empty():
                    try:
                        msg = self._inbound_queue.get_nowait()
                        tasks.append(self._handle_inbound(msg))
                    except asyncio.QueueEmpty:
                        pass

                # 处理出站消息
                if not self._outbound_queue.empty():
                    try:
                        msg = self._outbound_queue.get_nowait()
                        tasks.append(self._handle_outbound(msg))
                    except asyncio.QueueEmpty:
                        pass

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # 没有消息，小睡一会儿避免 CPU 空转
                    await asyncio.sleep(0.1)

            except Exception as e:
                self._stats["error_count"] += 1
                logger.exception(f"处理消息时出错: {e}")
                await asyncio.sleep(1)  # 出错后稍等

    async def _handle_inbound(self, message: InboundMessage) -> None:
        """处理入站消息，通知所有订阅者。"""
        try:
            # 先调用全局处理器
            for handler in self._global_inbound_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"全局入站处理器执行失败: {e}")

            # 再调用渠道特定处理器
            handlers = self._inbound_handlers.get(message.channel_name, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"渠道 {message.channel_name} 入站处理器执行失败: {e}")

        except Exception as e:
            self._stats["error_count"] += 1
            logger.exception(f"处理入站消息失败: {e}")

    async def _handle_outbound(self, message: OutboundMessage) -> None:
        """处理出站消息，通知所有订阅者。"""
        try:
            # 先调用全局处理器
            for handler in self._global_outbound_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"全局出站处理器执行失败: {e}")

            # 再调用渠道特定处理器
            handlers = self._outbound_handlers.get(message.channel_name, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"渠道 {message.channel_name} 出站处理器执行失败: {e}")

        except Exception as e:
            self._stats["error_count"] += 1
            logger.exception(f"处理出站消息失败: {e}")

    # =========================================================================
    # 工具方法
    # =========================================================================

    def get_stats(self) -> dict:
        """获取统计信息。"""
        return {
            **self._stats,
            "inbound_queue_size": self._inbound_queue.qsize(),
            "outbound_queue_size": self._outbound_queue.qsize(),
            "running": self._running,
        }

    def reset_stats(self) -> None:
        """重置统计信息。"""
        self._stats = {
            "inbound_count": 0,
            "outbound_count": 0,
            "error_count": 0,
        }
