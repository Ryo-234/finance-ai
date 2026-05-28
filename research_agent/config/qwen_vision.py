"""Qwen VL 视觉模型封装 - 支持图像理解。"""

import base64
import os
from typing import Any, Dict, List, Optional, Union
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun


class ChatQwenVL(BaseChatModel):
    """Qwen VL 视觉理解模型 - DashScope API。

    模型名称: qwen-vl-plus
    接口地址: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
    """

    model_name: str = "qwen-vl-plus"
    api_key: Optional[str] = None
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    temperature: float = 0.7
    max_tokens: int = 4096

    @property
    def _llm_type(self) -> str:
        return "qwen-vl"

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
        """异步生成。"""
        import requests

        api_key = self.api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")

        # 转换消息格式
        openai_messages = self._convert_to_openai_format(messages)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise ValueError(f"Qwen VL API error: {response.status_code} - {response.text}")

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def _convert_to_openai_format(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """将 LangChain 消息格式转换为 OpenAI 格式，支持图片。"""
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content
                # 支持混合内容（文本+图片）
                if isinstance(content, list):
                    result.append({"role": "user", "content": content})
                else:
                    result.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
        return result

    async def ainvoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        """异步调用接口。"""
        result = await self._agenerate(messages)
        return result.generations[0].message


def create_qwen_vl_model(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.7,
) -> ChatQwenVL:
    """创建 Qwen VL 模型实例。"""
    return ChatQwenVL(
        model_name=model_name or "qwen-vl-plus",
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
    if mime_type:
        return mime_type
    return "image/jpeg"


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
