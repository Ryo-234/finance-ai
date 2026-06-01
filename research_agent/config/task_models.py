"""按任务类型分级的模型选择器。

不同任务对模型能力要求不同：
- 简单任务（意图识别、问候回复）→ MiniMax-M2.7-highspeed（快、成本低）
- 中等任务（任务规划、知识整理）→ MiniMax-M2.7-highspeed
- 复杂任务（章节生成、报告综合）→ MiniMax-M3（质量高）

通过 env 变量覆盖：
- TASK_MODEL_SIMPLE = MiniMax-M2.7-highspeed
- TASK_MODEL_COMPLEX = MiniMax-M3
"""

import os
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    """任务复杂度。"""

    SIMPLE = "simple"        # 意图识别、问候回复、简单分类
    MEDIUM = "medium"        # 任务规划、知识整理、结构化提取
    COMPLEX = "complex"      # 章节生成、报告综合、深度分析


# 默认模型映射（按环境变量可覆盖）
DEFAULT_MODEL_MAP = {
    TaskComplexity.SIMPLE: os.getenv("TASK_MODEL_SIMPLE", "MiniMax-M2.7-highspeed"),
    TaskComplexity.MEDIUM: os.getenv("TASK_MODEL_MEDIUM", "MiniMax-M2.7-highspeed"),
    TaskComplexity.COMPLEX: os.getenv("TASK_MODEL_COMPLEX", "MiniMax-M3"),
}


def get_model_for_task(complexity: TaskComplexity) -> str:
    """获取指定复杂度任务应使用的模型名称。"""
    model = DEFAULT_MODEL_MAP.get(complexity, "MiniMax-M2.7-highspeed")
    logger.debug(f"任务复杂度 {complexity.value} -> 模型 {model}")
    return model


# 各 Agent 的复杂度预设（统一管理，避免散落）
AGENT_COMPLEXITY_MAP = {
    "planner": TaskComplexity.SIMPLE,                  # 意图+任务规划（fast）
    "finance_search": TaskComplexity.SIMPLE,            # 数据源查询（无 LLM）
    "finance_knowledge": TaskComplexity.MEDIUM,        # 知识整理
    "report_synthesizer": TaskComplexity.COMPLEX,      # 报告综合（高质量）
    "synthesizer": TaskComplexity.COMPLEX,              # 同上
}


def get_model_for_agent(agent_name: str) -> str:
    """根据 Agent 名称获取推荐模型。"""
    complexity = AGENT_COMPLEXITY_MAP.get(agent_name, TaskComplexity.MEDIUM)
    return get_model_for_task(complexity)


def create_model_for_task(complexity: TaskComplexity, temperature: Optional[float] = None):
    """为指定复杂度任务创建模型实例。"""
    from config.models import create_chat_model

    model_name = get_model_for_task(complexity)
    return create_chat_model(model_name=model_name, temperature=temperature)
