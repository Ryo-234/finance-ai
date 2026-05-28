"""Channel 模块初始化 - IM 渠道集成。"""

from channels.base import Channel
from channels.message_bus import MessageBus, InboundMessage, OutboundMessage, MessageType
from channels.manager import ChannelManager
from channels.feishu import FeishuChannel
from channels.service import (
    ChannelService,
    get_message_bus,
    get_channel_manager,
    init_channels,
    shutdown_channels,
)

__all__ = [
    # 基类
    "Channel",
    # 消息总线
    "MessageBus",
    "MessageType",
    "InboundMessage",
    "OutboundMessage",
    # 管理器
    "ChannelManager",
    # 渠道实现
    "FeishuChannel",
    # 服务
    "ChannelService",
    "get_message_bus",
    "get_channel_manager",
    "init_channels",
    "shutdown_channels",
]