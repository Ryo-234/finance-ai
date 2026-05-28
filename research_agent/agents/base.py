"""Agent 基类定义。"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field, asdict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage


def state_to_dict(state: Any) -> Dict[str, Any]:
    """将 state 转换为字典（兼容 dataclass 和 dict）。"""
    if isinstance(state, dict):
        return state
    if hasattr(state, '__dataclass_fields__'):
        return asdict(state)
    return {}


def state_get(state: Any, key: str, default: Any = None) -> Any:
    """从 state 获取值（兼容 dataclass 和 dict）。"""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


@dataclass
class AgentConfig:
    """Agent 配置类。"""

    name: str = "base_agent"
    description: str = "基础 Agent"
    model: Optional[BaseChatModel] = None
    temperature: float = 0.7
    system_prompt: str = ""


class BaseAgent(ABC):
    """所有 Agent 的基类。

    参考 DeerFlow 的 lead_agent 设计模式，
    提供标准化的 Agent 接口和生命周期管理。
    """

    def __init__(self, config: AgentConfig):
        """初始化 Agent。

        参数：
            config: Agent 配置
        """
        self.config = config
        self._model = config.model

    @property
    def name(self) -> str:
        """Agent 名称。"""
        return self.config.name

    @property
    def description(self) -> str:
        """Agent 描述。"""
        return self.config.description

    @property
    def model(self) -> BaseChatModel:
        """获取模型实例。"""
        if self._model is None:
            from config.models import create_chat_model
            self._model = create_chat_model()
        return self._model

    @model.setter
    def model(self, model: BaseChatModel) -> None:
        """设置模型实例。"""
        self._model = model

    @abstractmethod
    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        user_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        """异步执行 Agent。

        参数：
            state: 当前图状态
            user_input: 可选的用户输入

        返回：
            更新后的状态
        """
        pass

    def invoke(self, state: Dict[str, Any], *, user_input: Optional[str] = None) -> Dict[str, Any]:
        """同步执行 Agent（封装异步调用）。"""
        import asyncio
        return asyncio.run(self.ainvoke(state, user_input=user_input))

    def get_system_prompt(self) -> str:
        """获取系统提示词。子类可重写。"""
        return self.config.system_prompt