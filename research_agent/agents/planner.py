"""规划 Agent - 核心协调器。"""

import json
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from pydantic import BaseModel

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


# ============ Pydantic Schema 定义 ============
class TaskOutput(BaseModel):
    """LLM 输出的任务结构。"""
    needs_search: bool = False
    needs_rag: bool = False
    search_description: str = ""
    rag_description: str = ""
    reasoning: str = ""


@dataclass
class Task:
    """任务定义。"""
    id: str
    description: str
    task_type: str  # "search" / "rag" / "synthesize"
    status: str = "pending"  # "pending" / "running" / "completed" / "failed"
    result: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


class PlannerAgent(BaseAgent):
    """规划 Agent - 分析问题并拆解任务。

    这是研究助理的核心 Agent，负责：
    1. 理解用户问题
    2. 分析问题类型（搜索型/知识型/混合型）
    3. 拆解为可执行的子任务
    4. 决定任务执行顺序和依赖关系
    """

    def __init__(self, model=None):
        """初始化规划 Agent。"""
        super().__init__(
            config=AgentConfig(
                name="planner",
                description="规划 Agent - 分析问题并拆解任务",
                model=model,
                system_prompt="""你是一个智能研究助手的问题规划专家。

你的职责：
1. 理解用户的研究问题或问题
2. 分析问题类型：
   - 如果问题需要最新信息或网络资源 → needs_search = true
   - 如果问题需要特定领域知识 → needs_rag = true
   - 如果问题需要综合多种信息 → 两个都需要
3. 拆解任务并确定执行顺序

严格根据分析结果设置 needs_search 和 needs_rag。""",
            )
        )
        self._structured_model = None

    @property
    def structured_model(self):
        """获取支持结构化输出的模型。"""
        if self._structured_model is None:
            self._structured_model = self.model.with_structured_output(TaskOutput)
        return self._structured_model

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        user_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分析用户输入并创建任务计划。"""
        # 统一转换为字典
        state_dict = state_to_dict(state)

        # 获取用户输入
        if user_input is None:
            user_input = state_get(state_dict, "user_input", "")

        # 构建提示词
        prompt = f"""分析以下研究问题并制定执行计划：

问题：{user_input}

请分析：
1. 这个问题的核心需求是什么？
2. 需要哪些类型的 Agent 来解决？
3. 任务的执行顺序是什么？"""

        # 调用模型（结构化输出）
        try:
            response = await self.structured_model.ainvoke([
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=prompt),
            ])
            tasks = self._parse_structured_output(response, user_input)
            planner_output = response.reasoning or f"需要搜索: {response.needs_search}, 需要RAG: {response.needs_rag}"
        except Exception as e:
            # 结构化输出失败时降级到简单解析
            tasks = self._fallback_parse(user_input)
            planner_output = f"降级解析，原因: {str(e)}"

        # 更新状态
        return {
            **state_dict,
            "tasks": tasks,
            "current_task_index": 0,
            "planner_output": planner_output,
        }

    def _parse_structured_output(self, response: TaskOutput, original_input: str) -> List[Dict[str, Any]]:
        """解析结构化输出创建任务列表。"""
        tasks = []
        task_id_counter = 0

        if response.needs_search:
            tasks.append({
                "id": f"task_{task_id_counter}",
                "description": response.search_description or f"搜索相关信息：{original_input}",
                "task_type": "search",
                "status": "pending",
            })
            task_id_counter += 1

        if response.needs_rag:
            tasks.append({
                "id": f"task_{task_id_counter}",
                "description": response.rag_description or f"从知识库检索：{original_input}",
                "task_type": "rag",
                "status": "pending",
            })
            task_id_counter += 1

        # 始终添加综合任务
        tasks.append({
            "id": f"task_{task_id_counter}",
            "description": f"综合回答：{original_input}",
            "task_type": "synthesize",
            "status": "pending",
            "dependencies": [t["id"] for t in tasks] if tasks else [],
        })

        return tasks

    def _fallback_parse(self, original_input: str) -> List[Dict[str, Any]]:
        """降级解析：当结构化输出不可用时的备用方案。"""
        return [
            {
                "id": "task_0",
                "description": f"搜索相关信息：{original_input}",
                "task_type": "search",
                "status": "pending",
            },
            {
                "id": "task_1",
                "description": f"综合回答：{original_input}",
                "task_type": "synthesize",
                "status": "pending",
                "dependencies": ["task_0"],
            },
        ]

    def get_next_task(self, state: Dict[str, Any]) -> Optional[Task]:
        """获取下一个待执行的任务。"""
        state_dict = state_to_dict(state)
        tasks = state_get(state_dict, "tasks", [])
        current_index = state_get(state_dict, "current_task_index", 0)

        if current_index >= len(tasks):
            return None

        return tasks[current_index]

    def mark_task_complete(self, state: Dict[str, Any], task_id: str, result: str) -> Dict[str, Any]:
        """标记任务完成并更新状态。"""
        state_dict = state_to_dict(state)
        tasks = list(state_get(state_dict, "tasks", []))
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = "completed"
                task["result"] = result

        # 更新当前任务索引
        current_index = state_get(state_dict, "current_task_index", 0)
        return {
            **state_dict,
            "tasks": tasks,
            "current_task_index": current_index + 1,
        }