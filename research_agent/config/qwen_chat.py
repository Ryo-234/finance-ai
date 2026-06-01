"""通义千问 ChatModel 封装 - 继承 BaseChatModel。"""

import os
from typing import Any, AsyncGenerator, Optional, List, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun


class ChatQWen(BaseChatModel):
    """通义千问 ChatModel - 基于 DashScope SDK。"""

    model_name: str = "qwen-plus"
    temperature: float = 0.7
    max_tokens: int = 4096
    api_key: Optional[str] = None

    @property
    def _llm_type(self) -> str:
        return "qwen-chat"

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
        from dashscope import Generation

        # 转换消息格式
        qwen_messages = self._convert_to_qwen_format(messages)

        # 调用 DashScope
        response = Generation.call(
            model=self.model_name,
            messages=qwen_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            result_format='message',
            api_key=self.api_key or os.getenv("DASHSCOPE_API_KEY"),
        )

        if response.status_code != 200:
            raise ValueError(f"DashScope API error: {response.message}")

        # 解析响应
        content = response.output.choices[0].message.content
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def _convert_to_qwen_format(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """将 LangChain 消息格式转换为 DashScope 格式。"""
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            else:
                result.append({"role": "user", "content": str(msg.content)})
        return result

    async def ainvoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        """异步调用接口。"""
        result = await self._agenerate(messages)
        return result.generations[0].message

    async def astream(self, messages: List[BaseMessage], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用 —— 逐 token 生成。

        参数：
            messages: LangChain 消息列表

        产出：
            每个文本增量
        """
        from dashscope import Generation

        qwen_messages = self._convert_to_qwen_format(messages)

        responses = Generation.call(
            model=self.model_name,
            messages=qwen_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            result_format='message',
            api_key=self.api_key or os.getenv("DASHSCOPE_API_KEY"),
            stream=True,
            incremental_output=True,
        )

        for response in responses:
            if response.status_code != 200:
                raise ValueError(f"DashScope 流式 API 错误: {response.message}")
            msg = response.output.choices[0].message
            # incremental_output=True 时 content 是增量文本
            text = getattr(msg, 'content', '') or ''
            if text:
                yield text


def create_qwen_chat_model(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> ChatQWen:
    """创建通义千问 chat model 实例。"""
    from config.models import get_model_config

    config = get_model_config()
    return ChatQWen(
        model_name=model_name or config.default_model,
        temperature=temperature if temperature is not None else config.temperature,
        max_tokens=max_tokens or config.max_tokens,
        api_key=api_key or config.api_key,
    )
