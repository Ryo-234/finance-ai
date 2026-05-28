"""ViewImageMiddleware - 将图片数据注入到 LLM 调用。

工作流程：
1. 检查状态中的 viewed_images 是否有数据
2. 如果有，将图片的 base64 数据注入为一条新的 HumanMessage
3. 这样 LLM 就能"看到"图片内容并分析
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from middleware.base import BaseMiddleware

logger = logging.getLogger(__name__)


class ViewImageMiddleware(BaseMiddleware):
    """中间件：在 LLM 调用前注入图片数据。

    如果状态中有 viewed_images（由 Planner 检测并加载），
    则在消息前注入图片内容。
    """

    def __init__(self, enabled: bool = True, order: int = -8):
        super().__init__(enabled=enabled, order=order)
        self.name = "view_image"
        self.description = "将已读取的图片数据注入到 LLM 调用"

    def should_inject(self, state: Dict[str, Any]) -> bool:
        """检查是否需要注入图片消息。"""
        # 检查 viewed_images 是否有数据
        viewed_images = state.get("viewed_images", {})
        if not viewed_images:
            return False

        # 检查是否已经注入过
        messages = state.get("messages", [])
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str) and "以下是你已读取的图片" in content:
                    return False
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            if "以下是你已读取的图片" in block.get("text", ""):
                                return False

        return True

    def inject_image_message(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建包含图片数据的消息并返回。"""
        if not self.should_inject(state):
            return None

        viewed_images = state.get("viewed_images", {})
        if not viewed_images:
            return None

        # 构建混合内容消息（文本 + 图片）
        content_blocks = [{"type": "text", "text": "以下是你已读取的图片："}]

        for image_path, image_data in viewed_images.items():
            mime_type = image_data.get("mime_type", "image/jpeg")
            base64_data = image_data.get("base64", "")

            if not base64_data:
                continue

            # 添加图片路径文本
            content_blocks.append({
                "type": "text",
                "text": f"\n图片: {image_path} ({mime_type})"
            })

            # 添加图片数据（LLM 会识别 image_url 类型的内容）
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
            })

        # 创建 HumanMessage（包含混合内容）
        human_msg = HumanMessage(content=content_blocks)

        logger.info(f"注入图片消息，包含 {len(viewed_images)} 张图片")

        # 只返回消息，不清空 viewed_images（让 synthesizer 也能使用）
        return {
            "messages": [human_msg],
        }

    async def before_model(self, state: Dict[str, Any], runtime: Dict[str, Any]) -> Optional["MiddlewareResult"]:
        """在模型调用前执行。

        注入图片消息，并清空 viewed_images（避免后续重复注入）。
        """
        from middleware.base import MiddlewareResult

        viewed_images = state.get("viewed_images", {})
        if not viewed_images:
            return None

        # 检查是否已经注入过（避免重复注入）
        if not self.should_inject(state):
            # 已经注入过，清空 viewed_images
            return MiddlewareResult(updates={"viewed_images": {}})

        result = self.inject_image_message(state)
        if result is None:
            return None

        # 注入消息并清空 viewed_images
        result["viewed_images"] = {}
        return MiddlewareResult(updates=result)

    def list_middleware(self) -> Dict[str, Any]:
        """返回中间件信息。"""
        return {
            "name": self.name,
            "description": self.description,
            "enabled": True,
        }
