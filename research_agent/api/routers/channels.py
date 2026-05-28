"""通道管理路由 - 管理 IM 渠道。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from channels.service import get_channel_manager

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelStatus(BaseModel):
    """通道状态。"""
    name: str
    running: bool
    config: dict = Field(default_factory=dict)


class ChannelListResponse(BaseModel):
    """通道列表响应。"""
    channels: list[str]
    total: int


class SystemStatusResponse(BaseModel):
    """系统状态响应。"""
    running: bool
    channels: dict
    bus_stats: dict


# ============================================================================
# 通俗解释：什么是通道管理？
# ============================================================================
#
# 想象电视台系统：
# - 央视、北京台、上海台... = 不同的 IM 渠道（飞书、Telegram、Slack）
# - ChannelManager = 电视台总调度室
# - MessageBus = 卫星信号，把节目传到各家各户
#
# 我们做的：
# - 用户发消息到飞书 → 飞书通道收到 → MessageBus → Agent 处理
# - Agent 回复 → MessageBus → 飞书通道发送 → 用户收到
#
# ============================================================================


@router.get("/", response_model=ChannelListResponse)
async def list_channels():
    """列出所有已注册的通道。"""
    manager = get_channel_manager()
    channels = manager.list_channels()

    return ChannelListResponse(
        channels=channels,
        total=len(channels),
    )


@router.get("/status", response_model=SystemStatusResponse)
async def get_status():
    """获取通道系统状态。"""
    manager = get_channel_manager()
    status = manager.get_status()

    return SystemStatusResponse(
        running=status["running"],
        channels=status["channels"],
        bus_stats=status["bus_stats"],
    )


@router.get("/{channel_name}", response_model=ChannelStatus)
async def get_channel(channel_name: str):
    """获取指定通道的状态。"""
    manager = get_channel_manager()
    channel = manager.get_channel(channel_name)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_name} not found")

    return ChannelStatus(
        name=channel.name,
        running=channel.is_running,
        config=channel.get_config() if hasattr(channel, "get_config") else {},
    )


@router.post("/{channel_name}/start")
async def start_channel(channel_name: str):
    """启动指定通道。"""
    manager = get_channel_manager()
    channel = manager.get_channel(channel_name)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_name} not found")

    if channel.is_running:
        return {"success": True, "message": f"Channel {channel_name} is already running"}

    await channel.start()
    return {"success": True, "message": f"Channel {channel_name} started"}


@router.post("/{channel_name}/stop")
async def stop_channel(channel_name: str):
    """停止指定通道。"""
    manager = get_channel_manager()
    channel = manager.get_channel(channel_name)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_name} not found")

    if not channel.is_running:
        return {"success": True, "message": f"Channel {channel_name} is already stopped"}

    await channel.stop()
    return {"success": True, "message": f"Channel {channel_name} stopped"}


@router.post("/start-all")
async def start_all_channels():
    """启动所有通道。"""
    manager = get_channel_manager()
    await manager.start_all()
    return {"success": True, "message": "All channels started"}


@router.post("/stop-all")
async def stop_all_channels():
    """停止所有通道。"""
    manager = get_channel_manager()
    await manager.stop_all()
    return {"success": True, "message": "All channels stopped"}
