"""RAG Agent - 从知识库检索信息。"""

from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get


class RagAgent(BaseAgent):
    """RAG Agent - 从向量知识库检索相关信息。

    功能：
    1. 根据用户输入检索相关文档
    2. 提供上下文增强
    """

    def __init__(self, model=None):
        """初始化 RAG Agent。

        参数：
            model: 聊天模型实例
        """
        super().__init__(
            config=AgentConfig(
                name="rag",
                description="RAG Agent - 从知识库检索信息",
                model=model,
                system_prompt="""你是一个知识库检索助手。

你的职责：
1. 根据用户问题检索相关文档
2. 提供准确的上下文信息
3. 标注信息来源

请注意：
- 只返回与问题相关的信息
- 注明每个结果的来源""",
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从知识库检索信息。

        参数：
            state: 当前状态
            query: 查询语句（可选）

        返回：
            更新后的状态
        """
        state_dict = state_to_dict(state)

        if query is None:
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        return {
            **state_dict,
            "rag_query": query,
            "rag_results": [],
        }


def create_rag_agent(model=None) -> RagAgent:
    """创建 RAG Agent 的工厂函数。

    参数：
        model: 聊天模型实例

    返回：
        RagAgent 实例
    """
    return RagAgent(model=model)