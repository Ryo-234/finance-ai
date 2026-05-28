"""Channel 基类 - IM 渠道抽象。"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from channels.message_bus import InboundMessage, OutboundMessage


class Channel(ABC):
    """IM 渠道基类。

    所有 IM 渠道（飞书、Telegram、Slack 等）都继承这个类。

    核心流程：
    1. 接收消息 → 转换成 InboundMessage → 发到 MessageBus
    2. 从 MessageBus 订阅 OutboundMessage → 发送回渠道
    """

    def __init__(self, name: str, bus: "MessageBus", config: dict[str, Any]) -> None:
        """初始化渠道。

        Args:
            name: 渠道名称（如 "feishu", "telegram"）
            bus: 消息总线
            config: 配置字典
        """
        self.name = name
        self.bus = bus
        self.config = config
        self._running = False

    @property
    def is_running(self) -> bool:
        """是否正在运行。"""
        return self._running

    @abstractmethod
    async def start(self) -> None:
        """启动渠道。

        建立与 IM 服务器的连接（WebSocket/轮询等）。
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道。

        关闭连接，清理资源。
        """
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 IM。

        Args:
            msg: 要发送的消息
        """
        pass

    def _make_inbound(
        self,
        chat_id: str,
        user_id: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        files: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> InboundMessage:
        """创建入站消息。

        方便子类创建统一的 InboundMessage 格式。
        """
        return InboundMessage(
            channel_name=self.name,
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            thread_ts=thread_ts,
            files=files or [],
            metadata=metadata or {},
        )

    async def _on_outbound(self, msg: OutboundMessage) -> None:
        """处理出站消息回调。

        当 MessageBus 有发往这个渠道的消息时调用。
        只处理目标渠道是自己的消息。
        """
        if msg.channel_name == self.name:
            try:
                await self.send(msg)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(f"发送消息失败: {self.name}")