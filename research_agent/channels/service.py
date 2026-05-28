"""通道服务 - 管理通道生命周期的 FastAPI 依赖。"""

import asyncio
import logging
from typing import Optional

from channels.message_bus import MessageBus, InboundMessage, OutboundMessage
from channels.manager import ChannelManager
from channels.feishu import FeishuChannel

logger = logging.getLogger(__name__)

# 全局单例
_message_bus: Optional[MessageBus] = None
_channel_manager: Optional[ChannelManager] = None
_processing_task: Optional[asyncio.Task] = None


def get_message_bus() -> MessageBus:
    """获取消息总线单例。"""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
        logger.info("消息总线已创建")
    return _message_bus


def get_channel_manager() -> ChannelManager:
    """获取通道管理器单例。"""
    global _channel_manager
    if _channel_manager is None:
        bus = get_message_bus()
        _channel_manager = ChannelManager(bus)
        logger.info("通道管理器已创建")
    return _channel_manager


async def _create_agent_handler():
    """创建 Agent 消息处理器。"""
    from graph.research_graph import run_research
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()

    async def handle_message(inbound: InboundMessage) -> None:
        """处理收到的消息，调用 Agent 生成回复。"""
        logger.info(f"处理消息: chat_id={inbound.chat_id}, user_id={inbound.user_id}, text={inbound.text[:50]}...")

        try:
            # 获取消息中的文件信息
            files_metadata = inbound.metadata.get("files", [])

            # 构建用户输入（包含文件路径信息）
            user_input = inbound.text
            if files_metadata:
                file_paths = []
                for f in files_metadata:
                    if f.get("type") == "image":
                        file_paths.append(f.get("path", ""))
                if file_paths:
                    # 在用户输入中注入图片路径
                    paths_str = ", ".join(file_paths)
                    user_input = f"用户上传了图片: {paths_str}\n\n{user_input}"

            # 调用研究流程
            result = await run_research(
                user_input=user_input,
                thread_id=inbound.chat_id,  # 使用 chat_id 作为 thread_id
                user_id=inbound.user_id,
                checkpointer=checkpointer,
                files_metadata=files_metadata,
            )

            # 获取回复
            answer = result.get("answer", "抱歉，我无法回答这个问题。")

            # 创建回复消息
            reply = OutboundMessage(
                channel_name=inbound.channel_name,
                chat_id=inbound.chat_id,
                text=answer,
                thread_ts=inbound.thread_ts,  # 用于回复追踪
            )

            # 发布回复到总线
            bus = get_message_bus()
            await bus.publish_outbound(reply)
            logger.info(f"已发送回复到 {inbound.chat_id}: {answer[:50]}...")

        except Exception as e:
            logger.exception(f"处理消息失败: {e}")
            # 发送错误回复
            error_reply = OutboundMessage(
                channel_name=inbound.channel_name,
                chat_id=inbound.chat_id,
                text=f"处理消息时出错: {str(e)}",
                thread_ts=inbound.thread_ts,
            )
            bus = get_message_bus()
            await bus.publish_outbound(error_reply)

    return handle_message


async def init_channels(config: dict) -> None:
    """初始化并启动所有通道。

    Args:
        config: 通道配置字典，格式：
            {
                "feishu": {
                    "enabled": true,
                    "app_id": "...",
                    "app_secret": "...",
                },
                "telegram": {...},
            }
    """
    global _processing_task

    manager = get_channel_manager()
    bus = get_message_bus()

    # 获取或创建 Agent 消息处理器
    agent_handler = await _create_agent_handler()

    # 先移除旧的处理器（防止重复订阅）
    bus._global_inbound_handlers.clear()
    bus.subscribe_inbound("*", agent_handler)
    logger.info("Agent 消息处理器已注册")

    # 启动消息总线
    await bus.start()
    logger.info("消息总线已启动")

    # 初始化飞书
    feishu_config = config.get("feishu", {})
    if feishu_config.get("enabled", False):
        feishu_channel = FeishuChannel(
            name="feishu",
            bus=bus,
            config={
                "app_id": feishu_config.get("app_id"),
                "app_secret": feishu_config.get("app_secret"),
                "bot_name": feishu_config.get("bot_name", "DeerFlow Bot"),
            },
        )
        manager.register(feishu_channel)
        logger.info("飞书通道已注册")

    # TODO: 添加更多通道（Telegram、Slack 等）

    # 启动所有通道
    await manager.start_all()
    logger.info("所有通道已启动")


async def shutdown_channels() -> None:
    """关闭所有通道。"""
    global _channel_manager, _message_bus, _processing_task

    if _channel_manager:
        await _channel_manager.stop_all()
        _channel_manager = None
        logger.info("通道管理器已关闭")

    if _message_bus:
        await _message_bus.stop()
        _message_bus = None
        logger.info("消息总线已关闭")


class ChannelService:
    """通道服务类 - 用于 FastAPI 依赖注入。

    使用方式：
        @app.get("/channels")
        async def get_channels(service: ChannelService):
            return service.get_status()
    """

    def __init__(self) -> None:
        """初始化通道服务。"""
        self._manager = get_channel_manager()
        self._bus = get_message_bus()

    @property
    def manager(self) -> ChannelManager:
        """获取通道管理器。"""
        return self._manager

    @property
    def bus(self) -> MessageBus:
        """获取消息总线。"""
        return self._bus

    def get_status(self) -> dict:
        """获取通道状态。"""
        return self._manager.get_status()

    def list_channels(self) -> list[str]:
        """列出所有通道。"""
        return self._manager.list_channels()

    def get_channel_status(self, channel_name: str) -> Optional[dict]:
        """获取指定通道状态。"""
        channel = self._manager.get_channel(channel_name)
        if not channel:
            return None

        return {
            "name": channel.name,
            "running": channel.is_running,
            "config": channel.get_config() if hasattr(channel, "get_config") else {},
        }
