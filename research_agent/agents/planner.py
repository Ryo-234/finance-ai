"""规划 Agent - 核心协调器。"""

import json
import re
from typing import Any, Dict, Optional, List, Literal
from dataclasses import dataclass, field
from pydantic import BaseModel

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import JsonOutputParser


# ============ 意图类型定义 ============
class IntentType:
    GREETING = "greeting"           # 问候/闲聊
    CLARIFICATION = "clarification" # 需要澄清
    TASK = "task"                  # 任务请求
    UNKNOWN = "unknown"             # 未知


# ============ Pydantic Schema 定义 ============
class TaskOutput(BaseModel):
    """LLM 输出的任务结构。"""
    needs_search: bool = False
    needs_rag: bool = False
    search_description: str = ""
    rag_description: str = ""
    reasoning: str = ""


class IntentOutput(BaseModel):
    """LLM 意图分析输出（中文思考）。"""
    intent: Literal["task", "clarification", "greeting"] = "task"
    reasoning: str = ""  # 中文思考过程
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_type: Literal["missing_info", "ambiguous_requirement", "approach_choice", "risk_confirmation", "suggestion"] = "missing_info"
    clarification_options: List[str] = []
    clarification_context: str = ""


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
    5. 判断是否需要向用户澄清模糊请求
    """

    def __init__(self, model=None):
        """初始化规划 Agent。"""
        super().__init__(
            config=AgentConfig(
                name="planner",
                description="规划 Agent - 分析问题并拆解任务",
                model=model,
                system_prompt="""你是一个智能研究助手。

**工作流程：先理解 → 再判断 → 最后规划**

**意图识别规则（重要）：**
在制定计划之前，必须先判断用户的意图：
1. 如果用户只是问候（"你好"、"hi"等）→ intent = "greeting"
2. 如果用户在确认/回复之前的问题（如"好的"、"行"）→ 这是继续信号，不是新任务
3. 如果用户提出了新的明确任务 → intent = "task"
4. 如果用户请求不明确，缺少必要信息 → intent = "clarification"

**理解上下文的重要性：**
- 当用户说"好的"、"行"、"可以"时，通常是在确认你之前的建议
- 只有当用户明确提出新任务时，才创建新任务
- 不要把确认误判为新任务

**澄清规则（必须遵守）：**
只有在以下情况才需要澄清：
1. 缺少必要信息（没说搜索什么、没指定文件等）
2. 需求模糊（"随便"、"都可以"、指代不明）
3. 有多种可行方案需要选择
4. 涉及危险操作

**强制搜索规则（最高优先级）：**
以下类型的问题必须设置 needs_search=true，联网搜索获取最新信息：
1. 包含时效性关键词：最新、最近、今天、现在、当前、2026、今年
2. 涉及价格/促销/打折/优惠/活动
3. 涉及产品发布/更新/版本信息
4. 涉及新闻事件/时事热点
5. 任何你不确定答案、或答案可能随时间变化的问题
记住：你的训练数据是过时的，当用户问需要最新信息的问题时，必须联网搜索！

**返回格式要求：**
- intent: 意图类型（greeting/task/clarification）
- reasoning: 你的中文思考过程
- needs_clarification: 是否需要澄清
- 如果需要澄清，设置 clarification_question 等字段

严格根据分析结果返回。""",
            )
        )
        self._structured_model = None
        self._intent_model = None

    def _get_intent_parser(self):
        """获取意图分析输出解析器。"""
        return JsonOutputParser(pydantic_model=IntentOutput)

    def _get_task_parser(self):
        """获取任务规划输出解析器。"""
        return JsonOutputParser(pydantic_model=TaskOutput)

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        user_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分析用户输入并创建任务计划。

        根据完整对话上下文智能判断用户意图。
        """
        import logging
        logger = logging.getLogger(__name__)

        # 统一转换为字典
        state_dict = state_to_dict(state)

        # 获取用户输入
        if user_input is None:
            user_input = state_get(state_dict, "user_input", "")

        # 获取消息历史用于上下文理解
        messages = state_get(state_dict, "messages", [])

        # =====================================================================
        # 图片路径检测与处理
        # =====================================================================
        # 检测用户输入中的图片路径（格式：/mnt/user-data/uploads/xxx）
        image_paths = self._extract_image_paths(user_input)
        if image_paths:
            logger.info(f"检测到图片路径: {image_paths}")
            viewed_images = {}
            for path in image_paths:
                try:
                    from tools.view_image import read_image_as_base64
                    base64_data, mime_type = read_image_as_base64(path)
                    viewed_images[path] = {
                        "base64": base64_data,
                        "mime_type": mime_type,
                    }
                    logger.info(f"已加载图片: {path}")
                except Exception as e:
                    logger.warning(f"加载图片失败: {path}, error: {e}")
            if viewed_images:
                state_dict["viewed_images"] = viewed_images

        # =====================================================================
        # 意图分析与任务规划
        # =====================================================================

        # 构建完整的上下文提示
        context_prompt = self._build_context_prompt(user_input, messages)

        # 调用 LLM 进行意图分析和任务规划
        try:
            # 使用 JsonOutputParser 解析
            raw_response = await self.model.ainvoke(context_prompt)
            parser = self._get_intent_parser()
            response = parser.invoke(raw_response)
            logger.info(f"意图分析结果: intent={response.get('intent')}, reasoning={response.get('reasoning', '')}")
            state_dict["intent"] = response.get("intent", "task")

            # 如果需要澄清，返回澄清状态
            if response.get("needs_clarification") or response.get("intent") == IntentType.CLARIFICATION:
                return {
                    **state_dict,
                    "needs_clarification": True,
                    "clarification_question": response.get("clarification_question", ""),
                    "clarification_type": response.get("clarification_type", "missing_info"),
                    "clarification_options": response.get("clarification_options", []),
                    "clarification_context": response.get("clarification_context", ""),
                }

            # 如果是问候，返回问候响应
            if response.get("intent") == IntentType.GREETING:
                return {
                    **state_dict,
                    "intent": IntentType.GREETING,
                    "greeting_response": response.get("clarification_question") or self._get_greeting_response(),
                }

        except Exception as e:
            # 意图分析失败，继续到任务规划
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"意图分析失败: {e}")
            state_dict["intent_analysis_error"] = str(e)

        # 正常任务规划
        try:
            raw_response = await self.model.ainvoke(context_prompt)
            parser = self._get_task_parser()
            response = parser.invoke(raw_response)
            tasks = self._parse_structured_output(response, user_input)
            planner_output = response.get("reasoning") or f"需要搜索: {response.get('needs_search')}, 需要RAG: {response.get('needs_rag')}"
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

    def _build_context_prompt(self, user_input: str, messages: list) -> list:
        """构建包含完整上下文的提示。

        根据对话历史，让 LLM 能够理解多轮对话的上下文。
        """
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        # 构建对话历史摘要
        history_summary = self._summarize_conversation_history(messages)

        # 完整的分析提示
        analysis_prompt = f"""你是智能研究助手。请分析用户的最新输入，结合对话历史进行判断。

## 对话历史摘要：
{history_summary if history_summary else "（无历史记录，这是新一轮对话）"}

## 用户最新输入：
{user_input}

## 判断规则：

**1. 识别意图类型：**
- 如果用户只是问候（"你好"、"hi"等）→ intent = "greeting"
- 如果用户在确认/回复之前的问题（如"好的"、"行"、"可以"）→ 这通常是继续执行的信号
- 如果用户提出了新的明确任务 → intent = "task"
- 如果用户请求不明确，缺少必要信息 → intent = "clarification"

**2. 理解上下文的重要性：**
- 如果历史中有"我问你..."的问题，用户的回复很可能是确认
- 只有当用户明确表示要开始新任务时，才创建新任务
- 简单确认词（"好的"、"嗯"、"行"）通常表示同意之前的方案

**3. 澄清判断：**
只有在以下情况才需要澄清：
- 缺少必要信息（没说搜索什么、没指定文件等）
- 需求模糊（"随便"、"都可以"、指代不明）
- 有多种可行方案需要选择
- 涉及危险操作

请返回结构化的分析结果。"""

        return [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=analysis_prompt),
        ]

    def _summarize_conversation_history(self, messages: list) -> str:
        """总结对话历史，用于上下文理解。"""
        if not messages:
            return ""

        summary_parts = []
        for msg in messages[-6:]:  # 最近6条消息
            msg_type = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", "")

            # 截断过长内容
            if len(content) > 200:
                content = content[:200] + "..."

            if msg_type == "human":
                summary_parts.append(f"用户: {content}")
            elif msg_type == "ai":
                # 只显示 AI 的工具调用和关键回复
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                    summary_parts.append(f"助手: [调用工具: {', '.join(tool_names)}]")
                elif content:
                    summary_parts.append(f"助手: {content[:100]}...")

        return "\n".join(summary_parts) if summary_parts else ""

    def _extract_image_paths(self, text: str) -> list:
        """从文本中提取图片路径。

        支持的格式：
        - /mnt/user-data/uploads/xxx.jpg
        - /tmp/uploads/xxx.png
        - ./uploads/xxx.png
        - C:\\path\\to\\image.png

        Args:
            text: 用户输入文本

        Returns:
            图片路径列表
        """
        import re

        # 图片路径的正则模式
        patterns = [
            r'/mnt/user-data/uploads/[^\s]+\.(?:jpg|jpeg|png|gif|webp)',
            r'/tmp/uploads/[^\s]+\.(?:jpg|jpeg|png|gif|webp)',
            r'\./uploads/[^\s]+\.(?:jpg|jpeg|png|gif|webp)',
            r'[A-Za-z]:\\[^\s]+\.(?:jpg|jpeg|png|gif|webp)',
        ]

        paths = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            paths.extend(matches)

        # 去重
        return list(set(paths))

    def _get_greeting_response(self) -> str:
        """生成问候回复。"""
        import datetime
        hour = datetime.datetime.now().hour

        if 5 <= hour < 12:
            time_greeting = "早上好"
        elif 12 <= hour < 14:
            time_greeting = "中午好"
        elif 14 <= hour < 18:
            time_greeting = "下午好"
        else:
            time_greeting = "晚上好"

        return f"{time_greeting}！有什么我可以帮助你的吗？无论是搜索信息、分析问题还是其他研究任务，我都可以帮你完成。"

    def _parse_structured_output(self, response: Dict[str, Any], original_input: str) -> List[Dict[str, Any]]:
        """解析结构化输出创建任务列表。"""
        tasks = []
        task_id_counter = 0

        if response.get("needs_search", False):
            tasks.append({
                "id": f"task_{task_id_counter}",
                "description": response.get("search_description") or f"搜索相关信息：{original_input}",
                "task_type": "search",
                "status": "pending",
            })
            task_id_counter += 1

        if response.get("needs_rag", False):
            tasks.append({
                "id": f"task_{task_id_counter}",
                "description": response.get("rag_description") or f"从知识库检索：{original_input}",
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