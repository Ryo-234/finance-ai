"""MiniMax VL 视觉模型封装 - Token Plan 专用接口。"""

import base64
import os
from typing import Any, Dict, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun


class ChatMiniMaxVL(BaseChatModel):
    """MiniMax VL 视觉理解模型 - Token Plan 专用接口。

    接口地址: https://api.minimax.chat/v1/coding_plan/vlm
    请求格式: {"prompt": str, "image": "data:image/xxx;base64,..."}
    """

    model_name: str = "MiniMax-VL-01"
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096

    @property
    def _llm_type(self) -> str:
        return "minimax-vl-token-plan"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成。"""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self._agenerate(messages, stop, **kwargs))
            return result
        finally:
            loop.close()

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成 - Token Plan 专用格式。"""
        import requests

        api_key = self.api_key or os.getenv("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY 环境变量未设置")

        # 从消息中提取文本和图片
        prompt, image_data = self._extract_prompt_and_image(messages)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": prompt,
            "image": image_data,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        response = requests.post(
            "https://api.minimax.chat/v1/coding_plan/vlm",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise ValueError(f"MiniMax API error: {response.status_code} - {response.text}")

        result = response.json()
        content = result.get("content", "")

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def _extract_prompt_and_image(self, messages: List[BaseMessage]) -> tuple[str, str]:
        """从消息中提取 prompt 文本和图片数据。

        Returns:
            (prompt文本, image_data字符串)
        """
        prompt = ""
        image_data = ""

        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    prompt = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                prompt = block.get("text", "")
                            elif block.get("type") == "image_url":
                                image_url = block.get("image_url", {})
                                if isinstance(image_url, dict):
                                    image_data = image_url.get("url", "")
                                elif isinstance(image_url, str):
                                    image_data = image_url

        return prompt, image_data

    async def ainvoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        """异步调用接口。"""
        result = await self._agenerate(messages)
        return result.generations[0].message


def create_minimax_vl_model(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.7,
) -> ChatMiniMaxVL:
    """创建 MiniMax VL 模型实例。"""
    return ChatMiniMaxVL(
        model_name=model_name or "MiniMax-VL-01",
        api_key=api_key,
        temperature=temperature,
    )


def encode_image_to_base64(image_path: str) -> str:
    """将本地图片编码为 base64 字符串。"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def encode_image_from_bytes(image_bytes: bytes) -> str:
    """将图片字节数据编码为 base64 字符串。"""
    return base64.b64encode(image_bytes).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """根据文件扩展名获取 MIME 类型。"""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        return "image/jpeg"
    return mime_type


def build_image_data_url(image_path: str, mime_type: str = None) -> str:
    """构建图片的 data URL。

    Args:
        image_path: 图片文件路径
        mime_type: MIME 类型，如果为 None 则自动检测

    Returns:
        data:image/xxx;base64,xxxx 格式的字符串
    """
    if mime_type is None:
        mime_type = get_image_mime_type(image_path)

    base64_data = encode_image_to_base64(image_path)
    return f"data:{mime_type};base64,{base64_data}"
