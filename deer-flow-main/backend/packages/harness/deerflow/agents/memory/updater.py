"""用于读取、写入和更新记忆数据的 Memory 更新器。"""

import asyncio
import atexit
import concurrent.futures
import copy
import json
import logging
import math
import re
import uuid
from collections.abc import Awaitable
from typing import Any

from deerflow.agents.memory.prompt import (
    MEMORY_UPDATE_PROMPT,
    format_conversation_for_update,
)
from deerflow.agents.memory.storage import (
    create_empty_memory,
    get_memory_storage,
    utc_now_iso_z,
)
from deerflow.config.memory_config import get_memory_config
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)

# 同步 memory 更新器的线程池执行器
_SYNC_MEMORY_UPDATER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="memory-updater-sync",
)
# 注册进程退出时关闭执行器
atexit.register(lambda: _SYNC_MEMORY_UPDATER_EXECUTOR.shutdown(wait=False))


def _create_empty_memory() -> dict[str, Any]:
    """存储层空记忆工厂的向后兼容包装器。"""
    return create_empty_memory()


def _save_memory_to_file(memory_data: dict[str, Any], agent_name: str | None = None, *, user_id: str | None = None) -> bool:
    """已配置 memory 存储保存路径的向后兼容包装器。"""
    return get_memory_storage().save(memory_data, agent_name, user_id=user_id)


def get_memory_data(agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    """通过存储提供者获取当前记忆数据。"""
    return get_memory_storage().load(agent_name, user_id=user_id)


def reload_memory_data(agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    """通过存储提供者重新加载记忆数据。"""
    return get_memory_storage().reload(agent_name, user_id=user_id)


def import_memory_data(memory_data: dict[str, Any], agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    """通过存储提供者持久化导入的记忆数据。

    参数：
        memory_data: 要持久化的完整记忆数据。
        agent_name: 如果提供，导入到 per-agent 记忆。
        user_id: 如果提供，限定记忆到特定用户。

    返回：
        存储规范化后的已保存记忆数据。

    抛出：
        OSError: 如果持久化导入的记忆数据失败。
    """
    storage = get_memory_storage()
    if not storage.save(memory_data, agent_name, user_id=user_id):
        raise OSError("保存导入的记忆数据失败")
    return storage.load(agent_name, user_id=user_id)


def clear_memory_data(agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    """清除所有已存储的记忆数据并持久化一个空结构。"""
    cleared_memory = create_empty_memory()
    if not _save_memory_to_file(cleared_memory, agent_name, user_id=user_id):
        raise OSError("保存已清除的记忆数据失败")
    return cleared_memory


def _validate_confidence(confidence: float) -> float:
    """验证持久化的事实置信度，使存储的 JSON 保持标准兼容。"""
    if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
        raise ValueError("confidence")
    return confidence


def create_memory_fact(
    content: str,
    category: str = "context",
    confidence: float = 0.5,
    agent_name: str | None = None,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """创建新事实并持久化更新后的记忆数据。"""
    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("content")

    normalized_category = category.strip() or "context"
    validated_confidence = _validate_confidence(confidence)
    now = utc_now_iso_z()
    memory_data = get_memory_data(agent_name, user_id=user_id)
    updated_memory = dict(memory_data)
    facts = list(memory_data.get("facts", []))
    facts.append(
        {
            "id": f"fact_{uuid.uuid4().hex[:8]}",
            "content": normalized_content,
            "category": normalized_category,
            "confidence": validated_confidence,
            "createdAt": now,
            "source": "manual",
        }
    )
    updated_memory["facts"] = facts

    if not _save_memory_to_file(updated_memory, agent_name, user_id=user_id):
        raise OSError("创建事实后保存记忆数据失败")

    return updated_memory


def delete_memory_fact(fact_id: str, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    """按 ID 删除事实并持久化更新后的记忆数据。"""
    memory_data = get_memory_data(agent_name, user_id=user_id)
    facts = memory_data.get("facts", [])
    updated_facts = [fact for fact in facts if fact.get("id") != fact_id]
    if len(updated_facts) == len(facts):
        raise KeyError(fact_id)

    updated_memory = dict(memory_data)
    updated_memory["facts"] = updated_facts

    if not _save_memory_to_file(updated_memory, agent_name, user_id=user_id):
        raise OSError(f"删除事实 '{fact_id}' 后保存记忆数据失败")

    return updated_memory


def update_memory_fact(
    fact_id: str,
    content: str | None = None,
    category: str | None = None,
    confidence: float | None = None,
    agent_name: str | None = None,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """更新现有事实并持久化更新后的记忆数据。"""
    memory_data = get_memory_data(agent_name, user_id=user_id)
    updated_memory = dict(memory_data)
    updated_facts: list[dict[str, Any]] = []
    found = False

    for fact in memory_data.get("facts", []):
        if fact.get("id") == fact_id:
            found = True
            updated_fact = dict(fact)
            if content is not None:
                normalized_content = content.strip()
                if not normalized_content:
                    raise ValueError("content")
                updated_fact["content"] = normalized_content
            if category is not None:
                updated_fact["category"] = category.strip() or "context"
            if confidence is not None:
                updated_fact["confidence"] = _validate_confidence(confidence)
            updated_facts.append(updated_fact)
        else:
            updated_facts.append(fact)

    if not found:
        raise KeyError(fact_id)

    updated_memory["facts"] = updated_facts

    if not _save_memory_to_file(updated_memory, agent_name, user_id=user_id):
        raise OSError(f"更新事实 '{fact_id}' 后保存记忆数据失败")

    return updated_memory


def _extract_text(content: Any) -> str:
    """从 LLM 响应内容中提取纯文本（str 或内容块列表）。

    现代 LLM 可能返回结构化内容作为块列表而不是纯字符串，
    例如 [{"type": "text", "text": "..."}]。在这些内容上使用 str()
    会产生 Python repr 而不是实际文本，从而破坏下游的 JSON 解析。

    字符串块在连接时不使用分隔符，以避免破坏分块的 JSON/文本有效负载。
    基于字典的文本块被视为完整文本块，并用换行符连接以提高可读性。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        pending_str_parts: list[str] = []

        def flush_pending_str_parts() -> None:
            if pending_str_parts:
                pieces.append("".join(pending_str_parts))
                pending_str_parts.clear()

        for block in content:
            if isinstance(block, str):
                pending_str_parts.append(block)
            elif isinstance(block, dict):
                flush_pending_str_parts()
                text_val = block.get("text")
                if isinstance(text_val, str):
                    pieces.append(text_val)

        flush_pending_str_parts()
        return "\n".join(pieces)
    return str(content)


def _run_async_update_sync(coro: Awaitable[bool]) -> bool:
    """从同步代码运行异步记忆更新，包括嵌套循环上下文。"""
    handed_off = False

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            future = _SYNC_MEMORY_UPDATER_EXECUTOR.submit(asyncio.run, coro)
            handed_off = True
            return future.result()

        handed_off = True
        return asyncio.run(coro)
    except Exception:
        if not handed_off:
            close = getattr(coro, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.debug(
                        "关闭未等待的记忆更新协程失败",
                        exc_info=True,
                    )

        logger.exception("从同步上下文运行异步记忆更新失败")
        return False


# 匹配描述文件上传事件（而非一般文件相关工作）的句子。
# 有意保持狭窄，以避免删除合法事实，如"用户使用 CSV 文件工作"或"更喜欢 PDF 导出"。
_UPLOAD_SENTENCE_RE = re.compile(
    r"[^.!?]*\b(?:"
    r"upload(?:ed|ing)?(?:\s+\w+){0,3}\s+(?:file|files?|document|documents?|attachment|attachments?)"
    r"|file\s+upload"
    r"|/mnt/user-data/uploads/"
    r"|<uploaded_files>"
    r")[^.!?]*[.!?]?\s*",
    re.IGNORECASE,
)


def _strip_upload_mentions_from_memory(memory_data: dict[str, Any]) -> dict[str, Any]:
    """从所有记忆摘要和事实中移除关于文件上传的句子。

    上传的文件是会话作用域的；在长期记忆中持久化上传事件会导致
    agent 在后续会话中搜索不存在的文件。
    """
    # 清除 user/history 部分中的摘要
    for section in ("user", "history"):
        section_data = memory_data.get(section, {})
        for _key, val in section_data.items():
            if isinstance(val, dict) and "summary" in val:
                cleaned = _UPLOAD_SENTENCE_RE.sub("", val["summary"]).strip()
                cleaned = re.sub(r"  +", " ", cleaned)
                val["summary"] = cleaned

    # 同样移除描述上传事件的任何事实
    facts = memory_data.get("facts", [])
    if facts:
        memory_data["facts"] = [f for f in facts if not _UPLOAD_SENTENCE_RE.search(f.get("content", ""))]

    return memory_data


def _fact_content_key(content: Any) -> str | None:
    if not isinstance(content, str):
        return None
    stripped = content.strip()
    if not stripped:
        return None
    return stripped.casefold()


class MemoryUpdater:
    """基于对话上下文使用 LLM 更新记忆。"""

    def __init__(self, model_name: str | None = None):
        """初始化记忆更新器。

        参数：
            model_name: 要使用的可选模型名称。如果为 None，使用配置或默认模型。
        """
        self._model_name = model_name

    def _get_model(self):
        """获取用于记忆更新的模型。"""
        config = get_memory_config()
        model_name = self._model_name or config.model_name
        return create_chat_model(name=model_name, thinking_enabled=False)

    def _build_correction_hint(
        self,
        correction_detected: bool,
        reinforcement_detected: bool,
    ) -> str:
        """为纠正和强化信号构建可选的提示词提示。"""
        correction_hint = ""
        if correction_detected:
            correction_hint = (
                "重要：在此对话中检测到明确的纠正信号。 "
                "特别关注 agent 哪里做错了，用户纠正了什么，"
                "并将正确的方法记录为类别为 "
                '"correction" 且置信度 >= 0.95 的事实（适当时）。'
            )
        if reinforcement_detected:
            reinforcement_hint = (
                "重要：在此对话中检测到正向强化信号。 "
                "用户明确确认 agent 的方法是正确的或有帮助的。 "
                "将确认的方法、风格或偏好记录为类别为 "
                '"preference" 或 "behavior" 且置信度 >= 0.9 的事实（适当时）。'
            )
            correction_hint = (correction_hint + "\n" + reinforcement_hint).strip() if correction_hint else reinforcement_hint

        return correction_hint

    def _prepare_update_prompt(
        self,
        messages: list[Any],
        agent_name: str | None,
        correction_detected: bool,
        reinforcement_detected: bool,
    ) -> tuple[dict[str, Any], str] | None:
        """加载记忆并为对话构建更新提示词。"""
        config = get_memory_config()
        if not config.enabled or not messages:
            return None

        current_memory = get_memory_data(agent_name)
        conversation_text = format_conversation_for_update(messages)
        if not conversation_text.strip():
            return None

        correction_hint = self._build_correction_hint(
            correction_detected=correction_detected,
            reinforcement_detected=reinforcement_detected,
        )
        prompt = MEMORY_UPDATE_PROMPT.format(
            current_memory=json.dumps(current_memory, indent=2),
            conversation=conversation_text,
            correction_hint=correction_hint,
        )
        return current_memory, prompt

    def _finalize_update(
        self,
        current_memory: dict[str, Any],
        response_content: Any,
        thread_id: str | None,
        agent_name: str | None,
    ) -> bool:
        """解析模型响应，应用更新，并持久化记忆。"""
        response_text = _extract_text(response_content).strip()

        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        update_data = json.loads(response_text)
        # 在原地突变之前进行深拷贝，这样后续 save() 失败不会
        # 破坏仍被缓存的原始对象引用。
        updated_memory = self._apply_updates(copy.deepcopy(current_memory), update_data, thread_id)
        updated_memory = _strip_upload_mentions_from_memory(updated_memory)
        return get_memory_storage().save(updated_memory, agent_name)

    async def aupdate_memory(
        self,
        messages: list[Any],
        thread_id: str | None = None,
        agent_name: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
    ) -> bool:
        """基于对话消息异步更新记忆。"""
        try:
            prepared = await asyncio.to_thread(
                self._prepare_update_prompt,
                messages=messages,
                agent_name=agent_name,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
            if prepared is None:
                return False

            current_memory, prompt = prepared
            model = self._get_model()
            response = await model.ainvoke(prompt, config={"run_name": "memory_agent"})
            return await asyncio.to_thread(
                self._finalize_update,
                current_memory=current_memory,
                response_content=response.content,
                thread_id=thread_id,
                agent_name=agent_name,
            )
        except json.JSONDecodeError as e:
            logger.warning("解析 LLM 响应用于记忆更新失败：%s", e)
            return False
        except Exception as e:
            logger.exception("记忆更新失败：%s", e)
            return False

    def update_memory(
        self,
        messages: list[Any],
        thread_id: str | None = None,
        agent_name: str | None = None,
        correction_detected: bool = False,
        reinforcement_detected: bool = False,
        user_id: str | None = None,
    ) -> bool:
        """通过异步更新器路径同步更新记忆。

        参数：
            messages: 对话消息列表。
            thread_id: 用于跟踪来源的可选线程 ID。
            agent_name: 如果提供，更新 per-agent 记忆。如果为 None，更新全局记忆。
            correction_detected: 最近轮次是否包含明确的纠正信号。
            reinforcement_detected: 最近轮次是否包含正向强化信号。
            user_id: 如果提供，限定记忆到特定用户。

        返回：
            如果更新成功则返回 True，否则返回 False。
        """
        return _run_async_update_sync(
            self.aupdate_memory(
                messages=messages,
                thread_id=thread_id,
                agent_name=agent_name,
                correction_detected=correction_detected,
                reinforcement_detected=reinforcement_detected,
            )
        )

    def _apply_updates(
        self,
        current_memory: dict[str, Any],
        update_data: dict[str, Any],
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """将 LLM 生成的更新应用到记忆。

        参数：
            current_memory: 当前记忆数据。
            update_data: 来自 LLM 的更新。
            thread_id: 用于跟踪的可选线程 ID。

        返回：
            更新后的记忆数据。
        """
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
            current_memory["facts"] = [f for f in current_memory.get("facts", []) if f.get("id") not in facts_to_remove]

        # 添加新 facts
        existing_fact_keys = {fact_key for fact_key in (_fact_content_key(fact.get("content")) for fact in current_memory.get("facts", [])) if fact_key is not None}
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
                source_error = fact.get("sourceError")
                if isinstance(source_error, str):
                    normalized_source_error = source_error.strip()
                    if normalized_source_error:
                        fact_entry["sourceError"] = normalized_source_error
                current_memory["facts"].append(fact_entry)
                if fact_key is not None:
                    existing_fact_keys.add(fact_key)

        # 强制执行最大 facts 限制
        if len(current_memory["facts"]) > config.max_facts:
            # 按置信度排序并保留排名靠前的事实
            current_memory["facts"] = sorted(
                current_memory["facts"],
                key=lambda f: f.get("confidence", 0),
                reverse=True,
            )[: config.max_facts]

        return current_memory


def update_memory_from_conversation(
    messages: list[Any],
    thread_id: str | None = None,
    agent_name: str | None = None,
    correction_detected: bool = False,
    reinforcement_detected: bool = False,
    user_id: str | None = None,
) -> bool:
    """从对话更新记忆的便捷函数。

    参数：
        messages: 对话消息列表。
        thread_id: 可选线程 ID。
        agent_name: 如果提供，更新 per-agent 记忆。如果为 None，更新全局记忆。
        correction_detected: 最近轮次是否包含明确的纠正信号。
        reinforcement_detected: 最近轮次是否包含正向强化信号。
        user_id: 如果提供，限定记忆到特定用户。

    返回：
        如果成功则返回 True，否则返回 False。
    """
    updater = MemoryUpdater()
    return updater.update_memory(messages, thread_id, agent_name, correction_detected, reinforcement_detected, user_id=user_id)