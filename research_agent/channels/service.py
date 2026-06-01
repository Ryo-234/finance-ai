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


# 飞书渠道命令前缀 → 报告类型映射
FEISHU_COMMAND_MAP = {
    "/company": "company_deep",
    "/industry": "industry_research",
    "/macro": "macro_brief",
    "/strategy": "strategy_daily",
    "/公司": "company_deep",
    "/行业": "industry_research",
    "/宏观": "macro_brief",
    "/策略": "strategy_daily",
}

REPORT_TYPE_LABELS = {
    "company_deep": "公司深度",
    "industry_research": "行业研究",
    "macro_brief": "宏观简报",
    "strategy_daily": "策略日报",
}


def _parse_feishu_command(text: str) -> tuple[str, str]:
    """解析飞书消息中的命令前缀。

    返回：(实际研究课题, 报告类型)
    """
    text = text.strip()
    for prefix, report_type in FEISHU_COMMAND_MAP.items():
        if text.startswith(prefix):
            return text[len(prefix):].strip(), report_type
    return text, "company_deep"  # 默认公司深度


async def _create_agent_handler():
    """创建 Agent 消息处理器。"""
    from graph.research_graph import run_research, run_finance_research
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()

    async def handle_message(inbound: InboundMessage) -> None:
        """处理收到的消息，调用 Agent 生成回复。"""
        logger.info(f"处理消息: chat_id={inbound.chat_id}, user_id={inbound.user_id}, text={inbound.text[:50]}...")

        bus = get_message_bus()

        try:
            # 获取消息中的文件信息
            files_metadata = inbound.metadata.get("files", [])

            # 解析命令前缀（飞书专用：/company 等）
            topic, report_type = _parse_feishu_command(inbound.text)

            if not topic:
                # 只有命令没有内容
                await bus.publish_outbound(OutboundMessage(
                    channel_name=inbound.channel_name,
                    chat_id=inbound.chat_id,
                    text="请输入研究课题，例如：\n/company 贵州茅台 600519 基本面分析\n/industry 新能源汽车 2025 趋势\n/macro 中国 Q1 宏观经济\n/strategy 今日 A 股策略",
                    thread_ts=inbound.thread_ts,
                ))
                return

            # 构建用户输入
            user_input = topic
            if files_metadata:
                file_paths = []
                for f in files_metadata:
                    if f.get("type") == "image":
                        file_paths.append(f.get("path", ""))
                if file_paths:
                    paths_str = ", ".join(file_paths)
                    user_input = f"用户上传了图片: {paths_str}\n\n{user_input}"

            # 发送"正在处理"提示（避免飞书超时）
            type_label = REPORT_TYPE_LABELS.get(report_type, "研究报告")
            await bus.publish_outbound(OutboundMessage(
                channel_name=inbound.channel_name,
                chat_id=inbound.chat_id,
                text=f"🔄 正在生成【{type_label}】报告...\n课题：{topic[:80]}\n预计需要 30-60 秒",
                thread_ts=inbound.thread_ts,
            ))

            # 异步任务：调用金融投研流水线（不阻塞消息总线）
            async def run_finance():
                try:
                    result = await run_finance_research(
                        user_input=user_input,
                        thread_id=inbound.chat_id,
                        report_type=report_type,
                        user_id=inbound.user_id,
                        plan_type="free",  # 飞书渠道默认 free
                    )
                    answer = result.get("answer", "抱歉，生成报告时遇到问题。")
                    compliance = result.get("compliance_checked", False)
                    compliance_tag = "✅ 合规通过\n\n" if compliance else ""

                    final = (
                        f"📊 已生成【{type_label}】报告\n\n"
                        f"{compliance_tag}{answer}"
                    )

                    # 飞书消息有长度限制（默认 4000 字符），过长时分段
                    MAX_LEN = 3500
                    if len(final) <= MAX_LEN:
                        await bus.publish_outbound(OutboundMessage(
                            channel_name=inbound.channel_name,
                            chat_id=inbound.chat_id,
                            text=final,
                            thread_ts=inbound.thread_ts,
                        ))
                    else:
                        # 分段发送
                        for i in range(0, len(final), MAX_LEN):
                            chunk = final[i:i + MAX_LEN]
                            await bus.publish_outbound(OutboundMessage(
                                channel_name=inbound.channel_name,
                                chat_id=inbound.chat_id,
                                text=chunk,
                                thread_ts=inbound.thread_ts,
                            ))
                            await asyncio.sleep(0.5)

                    logger.info(f"已发送金融报告到 {inbound.chat_id}")
                except Exception as e:
                    logger.exception(f"飞书金融研究失败: {e}")
                    await bus.publish_outbound(OutboundMessage(
                        channel_name=inbound.channel_name,
                        chat_id=inbound.chat_id,
                        text=f"❌ 生成报告失败：{str(e)[:200]}",
                        thread_ts=inbound.thread_ts,
                    ))

            # 提交异步任务，不阻塞 handle_message 返回
            asyncio.create_task(run_finance())

        except Exception as e:
            logger.exception(f"处理消息失败: {e}")
            await bus.publish_outbound(OutboundMessage(
                channel_name=inbound.channel_name,
                chat_id=inbound.chat_id,
                text=f"处理消息时出错: {str(e)[:200]}",
                thread_ts=inbound.thread_ts,
            ))

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
