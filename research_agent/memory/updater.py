"""Memory 更新器 - LLM 驱动的记忆更新引擎。"""

import asyncio
import concurrent.futures
import copy
import json
import logging
import math
import re
import uuid
from collections.abc import Awaitable
from typing import Any, Optional

from memory.storage import get_memory_storage, create_empty_memory, utc_now_iso_z

logger = logging.getLogger(__name__)

# 线程池用于异步更新
_SYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
import atexit
atexit.register(lambda: _SYNC_EXECUTOR.shutdown(wait=False))


MEMORY_UPDATE_PROMPT = """你是一个记忆管理系统。你的任务是分析对话并更新用户记忆。

当前记忆状态：
<current_memory>
{current_memory}
</current_memory>

新对话：
<conversation>
{conversation}
</conversation>

指导原则：
1. 分析对话中的重要用户信息
2. 提取具体事实、偏好和上下文
3. 更新记忆部分

记忆结构：
- workContext: 工作相关上下文（简洁）
- personalContext: 个人偏好（简洁）
- topOfMind: 当前关注点（详细）
- history: 历史信息（详细）
- facts: 具体事实列表

输出格式（JSON）：
{{
  "user": {{
    "workContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "personalContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "topOfMind": {{ "summary": "...", "shouldUpdate": true/false }}
  }},
  "history": {{
    "recentMonths": {{ "summary": "...", "shouldUpdate": true/false }},
    "earlierContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "longTermBackground": {{ "summary": "...", "shouldUpdate": true/false }}
  }},
  "newFacts": [
    {{ "content": "...", "category": "preference|knowledge|context|behavior|goal", "confidence": 0.0-1.0 }}
  ],
  "factsToRemove": ["fact_id_1", "fact_id_2"]
}}

只返回有效 JSON，无解释。"""


def format_conversation_for_update(messages: list[Any]) -> str:
    """格式化对话消息。"""
    lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))

        # 处理多模态内容
        if isinstance(content, list):
            text_parts = []
            for p in content:
                if isinstance(p, str):
                    text_parts.append(p)
                elif isinstance(p, dict):
                    text_val = p.get("text")
                    if isinstance(text_val, str):
                        text_parts.append(text_val)
            content = " ".join(text_parts) if text_parts else str(content)

        # 剥离上传文件标签
        if role == "human":
            content = re.sub(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", "", str(content)).strip()
            if not content:
                continue

        if len(str(content)) > 1000:
            content = str(content)[:1000] + "..."

        if role == "human":
            lines.append(f"User: {content}")
        elif role == "ai":
            lines.append(f"Assistant: {content}")

    return "\n\n".join(lines)


def _coerce_confidence(value: Any, default: float = 0.0) -> float:
    """将值强制转换为 [0, 1] 范围内的浮点数。"""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return max(0.0, min(1.0, default))
    if not math.isfinite(confidence):
        return max(0.0, min(1.0, default))
    return max(0.0, min(1.0, confidence))


def _fact_content_key(content: Any) -> Optional[str]:
    """生成事实内容键用于去重。"""
    if not isinstance(content, str):
        return None
    stripped = content.strip()
    if not stripped:
        return None
    return stripped.casefold()


def _extract_text(content: Any) -> str:
    """从 LLM 响应中提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for block in content:
            if isinstance(block, str):
                pieces.append(block)
            elif isinstance(block, dict):
                text_val = block.get("text")
                if isinstance(text_val, str):
                    pieces.append(text_val)
        return "\n".join(pieces)
    return str(content)


class MemoryUpdater:
    """基于对话上下文使用 LLM 更新记忆。"""

    def __init__(self, model_name: Optional[str] = None):
        """初始化记忆更新器。"""
        self._model_name = model_name

    def _get_model(self):
        """获取用于记忆更新的模型。"""
        from config.models import create_chat_model
        from config.memory import get_memory_config

        config = get_memory_config()
        model_name = self._model_name or config.model_name
        return create_chat_model(model_name=model_name)

    async def aupdate_memory(
        self,
        messages: list[Any],
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> bool:
        """异步更新记忆。"""
        try:
            # 加载当前记忆
            storage = get_memory_storage()
            current_memory = storage.load(user_id)

            # 格式化对话
            conversation_text = format_conversation_for_update(messages)
            if not conversation_text.strip():
                return False

            # 构建提示词
            prompt = MEMORY_UPDATE_PROMPT.format(
                current_memory=json.dumps(current_memory, indent=2),
                conversation=conversation_text,
            )

            # 调用 LLM
            model = self._get_model()
            response = await model.ainvoke(prompt)

            # 解析响应
            response_text = _extract_text(response.content).strip()

            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            update_data = json.loads(response_text)

            # 应用更新
            updated_memory = self._apply_updates(copy.deepcopy(current_memory), update_data, thread_id)

            # 保存
            return storage.save(updated_memory, user_id)

        except json.JSONDecodeError as e:
            logger.warning("解析 LLM 响应失败：%s", e)
            return False
        except Exception as e:
            logger.exception("记忆更新失败：%s", e)
            return False

    def _apply_updates(
        self,
        current_memory: dict[str, Any],
        update_data: dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """应用 LLM 生成的更新到记忆。"""
        from config.memory import get_memory_config

        config = get_memory_config()
        now = utc_now_iso_z()

        # 更新 user 部分
        user_updates = update_data.get("user", {})
        for section in ["workContext", "personalContext", "topOfMind"]:
            section_data = user_updates.get(section, {})
            if section_data.get("shouldUpdate") and section_data.get("summary"):
                current_memory["user"][section] = {
                    "summary": section_data["summary"],
                    "updatedAt": now,
                }

        # 更新 history 部分
        history_updates = update_data.get("history", {})
        for section in ["recentMonths", "earlierContext", "longTermBackground"]:
            section_data = history_updates.get(section, {})
            if section_data.get("shouldUpdate") and section_data.get("summary"):
                current_memory["history"][section] = {
                    "summary": section_data["summary"],
                    "updatedAt": now,
                }

        # 删除 facts
        facts_to_remove = set(update_data.get("factsToRemove", []))
        if facts_to_remove:
            current_memory["facts"] = [
                f for f in current_memory.get("facts", []) if f.get("id") not in facts_to_remove
            ]

        # 添加新 facts
        existing_fact_keys = {
            fact_key
            for fact_key in (
                _fact_content_key(fact.get("content"))
                for fact in current_memory.get("facts", [])
            )
            if fact_key is not None
        }

        new_facts = update_data.get("newFacts", [])
        for fact in new_facts:
            confidence = fact.get("confidence", 0.5)
            if confidence >= config.fact_confidence_threshold:
                raw_content = fact.get("content", "")
                if not isinstance(raw_content, str):
                    continue

                normalized_content = raw_content.strip()
                fact_key = _fact_content_key(normalized_content)
                if fact_key is not None and fact_key in existing_fact_keys:
                    continue

                fact_entry = {
                    "id": f"fact_{uuid.uuid4().hex[:8]}",
                    "content": normalized_content,
                    "category": fact.get("category", "context"),
                    "confidence": confidence,
                    "createdAt": now,
                    "source": thread_id or "unknown",
                }
                current_memory["facts"].append(fact_entry)
                if fact_key is not None:
                    existing_fact_keys.add(fact_key)

        # 强制执行最大 facts 限制
        if len(current_memory["facts"]) > config.max_facts:
            current_memory["facts"] = sorted(
                current_memory["facts"],
                key=lambda f: f.get("confidence", 0),
                reverse=True,
            )[: config.max_facts]

        return current_memory

    def update_memory(
        self,
        messages: list[Any],
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> bool:
        """同步更新记忆（通过异步路径）。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.aupdate_memory(
                    messages=messages,
                    thread_id=thread_id,
                    user_id=user_id,
                    correction_detected=correction_detected,
                    reinforcement_detected=reinforcement_detected,
                )
            )

        if loop.is_running():
            future = _SYNC_EXECUTOR.submit(
                asyncio.run,
                self.aupdate_memory(
                    messages=messages,
                    thread_id=thread_id,
                    user_id=user_id,
                    correction_detected=correction_detected,
                    reinforcement_detected=reinforcement_detected,
                )
            )
            return future.result()

        return asyncio.run(
            self.aupdate_memory(
                messages=messages,
                thread_id=thread_id,
                user_id=user_id,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
        )


def get_memory_data(user_id: str | None = None) -> dict[str, Any]:
    """获取当前记忆数据。"""
    return get_memory_storage().load(user_id)


def update_memory_from_conversation(
    messages: list[Any],
    thread_id: str | None = None,
    user_id: str | None = None,
    correction_detected: bool = False,
    reinforcement_detected: bool = False,
) -> bool:
    """从对话更新记忆的便捷函数。"""
    updater = MemoryUpdater()
    return updater.update_memory(
        messages=messages,
        thread_id=thread_id,
        user_id=user_id,
        correction_detected=correction_detected,
        reinforcement_detected=reinforcement_detected,
    )