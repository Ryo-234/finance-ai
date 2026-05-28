"""通道管理器 - 统一管理所有 IM 渠道。"""

import asyncio
import logging
from typing import Optional

from channels.base import Channel
from channels.message_bus import MessageBus, OutboundMessage

logger = logging.getLogger(__name__)


class ChannelManager:
    """通道管理器 - 统一管理所有 IM 渠道的生命周期。

    通俗理解：
    - ChannelManager = 电视台总调度室
    - Channel = 各个地方电视台（央视、北京台、上海台...）
    - MessageBus = 卫星信号（把节目信号发送到各家各户）

    工作流程：
    1. 启动时，注册所有渠道（Feishu、Telegram、Slack...）
    2. 每个渠道收到消息 → 发到 MessageBus
    3. MessageBus 分发给 Agent 处理
    4. Agent 回复 → MessageBus → 相应渠道发送

    一对多关系：
    - 1 个 ChannelManager 管理 N 个 Channel
    - 1 个 MessageBus 服务所有 Channel
    """

    def __init__(self, bus: MessageBus) -> None:
        """初始化通道管理器。

        Args:
            bus: 消息总线实例
        """
        self._bus = bus
        self._channels: dict[str, Channel] = {}
        self._running = False

        # 注册出站消息处理器（把 Agent 的回复发到对应渠道）
        self._bus.subscribe_outbound("*", self._on_outbound_message)

    @property
    def is_running(self) -> bool:
        """是否正在运行。"""
        return self._running

    @property
    def bus(self) -> MessageBus:
        """获取消息总线。"""
        return self._bus

    # =========================================================================
    # 渠道注册
    # =========================================================================

    def register(self, channel: Channel) -> None:
        """注册一个渠道。

        Args:
            channel: 渠道实例（FeishuChannel、TelegramChannel 等）
        """
        if channel.name in self._channels:
            logger.warning(f"渠道 {channel.name} 已存在，将被替换")

        self._channels[channel.name] = channel
        logger.info(f"渠道已注册: {channel.name}")

    def unregister(self, channel_name: str) -> None:
        """注销一个渠道。

        Args:
            channel_name: 渠道名称
        """
        if channel_name in self._channels:
            channel = self._channels.pop(channel_name)
            logger.info(f"渠道已注销: {channel_name}")
        else:
            logger.warning(f"渠道不存在: {channel_name}")

    def get_channel(self, channel_name: str) -> Optional[Channel]:
        """获取指定渠道。

        Args:
            channel_name: 渠道名称

        Returns:
            渠道实例，不存在返回 None
        """
        return self._channels.get(channel_name)

    def list_channels(self) -> list[str]:
        """列出所有已注册的渠道名称。"""
        return list(self._channels.keys())

    # =========================================================================
    # 生命周期管理
    # =========================================================================

    async def start_all(self) -> None:
        """启动所有渠道。"""
        if self._running:
            logger.warning("通道管理器已在运行")
            return

        self._running = True

        # 启动消息总线
        await self._bus.start()

        # 启动所有渠道
        tasks = []
        for channel in self._channels.values():
            if not channel.is_running:
                tasks.append(channel.start())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"已启动 {len(tasks)} 个渠道")

    async def stop_all(self) -> None:
        """停止所有渠道。"""
        if not self._running:
            return

        self._running = False

        # 停止所有渠道
        tasks = []
        for channel in self._channels.values():
            if channel.is_running:
                tasks.append(channel.stop())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 停止消息总线
        await self._bus.stop()

        logger.info("所有渠道已停止")

    # =========================================================================
    # 消息处理
    # =========================================================================

    async def _on_outbound_message(self, msg: OutboundMessage) -> None:
        """处理出站消息回调。

        当 Agent 发消息时，MessageBus 会调用这个方法。
        我们把消息路由到对应的渠道去发送。

        Args:
            msg: 出站消息
        """
        channel = self._channels.get(msg.channel_name)
        if not channel:
            logger.error(f"未找到渠道: {msg.channel_name}")
            return

        if not channel.is_running:
            logger.error(f"渠道未运行: {msg.channel_name}")
            return

        try:
            await channel.send(msg)
        except Exception as e:
            logger.exception(f"渠道 {msg.channel_name} 发送消息失败: {e}")

    # =========================================================================
    # 工具方法
    # =========================================================================

    def get_status(self) -> dict:
        """获取所有渠道的状态。"""
        return {
            "running": self._running,
            "channels": {
                name: {
                    "running": channel.is_running,
                    "name": channel.name,
                }
                for name, channel in self._channels.items()
            },
            "bus_stats": self._bus.get_stats(),
        }
