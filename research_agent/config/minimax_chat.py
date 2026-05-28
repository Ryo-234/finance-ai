"""MiniMax ChatModel 封装 - Token Plan M2.7 模型。"""

import os
from typing import Any, Dict, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun


class ChatMiniMax(BaseChatModel):
    """MiniMax ChatModel - 基于 OpenAI 兼容接口。

    使用 Token Plan 的 MiniMax-M2.7 模型。
    接口地址: https://api.minimax.chat/v1/chat/completions
    """

    model_name: str = "MiniMax-M2.7-highspeed"
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096

    @property
    def _llm_type(self) -> str:
        return "minimax-chat"

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

        api_key = self.api_key or os.getenv("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY 环境变量未设置")

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
            "https://api.minimax.chat/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise ValueError(f"MiniMax API error: {response.status_code} - {response.text}")

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def _convert_to_openai_format(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """将 LangChain 消息格式转换为 OpenAI 格式。"""
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content
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


def create_minimax_chat_model(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
) -> ChatMiniMax:
    """创建 MiniMax chat model 实例。"""
    return ChatMiniMax(
        model_name=model_name or "MiniMax-M2.7",
        api_key=api_key,
        temperature=temperature or 0.7,
    )
