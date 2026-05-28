"""Memory 提示词模板。"""

import tiktoken
from typing import Any

# 全局编码器缓存
_encoder = None


def _get_encoder():
    """获取 tiktoken 编码器（懒加载）。"""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """使用 tiktoken 精确计算 token 数量。"""
    encoder = _get_encoder()
    return len(encoder.encode(text))


def truncate_text(text: str, max_tokens: int) -> str:
    """按 token 数量截断文本。"""
    encoder = _get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # 保留 95% 的 token，留点余量
    truncated_tokens = tokens[: int(max_tokens * 0.95)]
    return encoder.decode(truncated_tokens)


def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
    """格式化记忆数据以注入到系统提示词中。

    参数：
        memory_data: 记忆数据字典
        max_tokens: 最大 token 数量

    返回：
        格式化后的记忆字符串
    """
    if not memory_data:
        return ""

    sections = []

    # 格式化 user context
    user_data = memory_data.get("user", {})
    if user_data:
        user_sections = []

        work_ctx = user_data.get("workContext", {})
        if work_ctx.get("summary"):
            user_sections.append(f"Work: {work_ctx['summary']}")

        personal_ctx = user_data.get("personalContext", {})
        if personal_ctx.get("summary"):
            user_sections.append(f"Personal: {personal_ctx['summary']}")

        top_of_mind = user_data.get("topOfMind", {})
        if top_of_mind.get("summary"):
            user_sections.append(f"Current Focus: {top_of_mind['summary']}")

        if user_sections:
            sections.append("User Context:\n" + "\n".join(f"- {s}" for s in user_sections))

    # 格式化 history
    history_data = memory_data.get("history", {})
    if history_data:
        history_sections = []

        recent = history_data.get("recentMonths", {})
        if recent.get("summary"):
            history_sections.append(f"Recent: {recent['summary']}")

        earlier = history_data.get("earlierContext", {})
        if earlier.get("summary"):
            history_sections.append(f"Earlier: {earlier['summary']}")

        background = history_data.get("longTermBackground", {})
        if background.get("summary"):
            history_sections.append(f"Background: {background['summary']}")

        if history_sections:
            sections.append("History:\n" + "\n".join(f"- {s}" for s in history_sections))

    # 格式化 facts
    facts_data = memory_data.get("facts", [])
    if isinstance(facts_data, list) and facts_data:
        # 按置信度排序
        ranked_facts = sorted(
            (f for f in facts_data if isinstance(f, dict) and f.get("content", "").strip()),
            key=lambda fact: fact.get("confidence", 0.0),
            reverse=True,
        )

        fact_lines = []
        for fact in ranked_facts[:15]:  # 最多 15 个 facts
            content = fact.get("content", "").strip()
            category = fact.get("category", "context")
            confidence = fact.get("confidence", 0.0)
            fact_lines.append(f"- [{category} | {confidence:.2f}] {content}")

        if fact_lines:
            sections.append("Facts:\n" + "\n".join(fact_lines))

    if not sections:
        return ""

    result = "\n\n".join(sections)

    # 使用 tiktoken 精确计算 token 数量
    total_tokens = count_tokens(result)
    if total_tokens > max_tokens:
        result = truncate_text(result, max_tokens)

    return result