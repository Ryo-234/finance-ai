"""消息处理辅助函数。"""

from __future__ import annotations

import re
from copy import copy
from typing import Any


# 上传文件块正则
_UPLOAD_BLOCK_RE = re.compile(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", re.IGNORECASE)

# 纠正模式
_CORRECTION_PATTERNS = (
    re.compile(r"\bthat(?:'s| is) (?:wrong|incorrect)\b", re.IGNORECASE),
    re.compile(r"\byou misunderstood\b", re.IGNORECASE),
    re.compile(r"\btry again\b", re.IGNORECASE),
    re.compile(r"\bredo\b", re.IGNORECASE),
    re.compile(r"不对"),
    re.compile(r"你理解错了"),
    re.compile(r"你理解有误"),
    re.compile(r"重试"),
)

# 强化模式
_REINFORCEMENT_PATTERNS = (
    re.compile(r"\b(?:yes|perfect|exactly)\b", re.IGNORECASE),
    re.compile(r"\bthis is (?:great|helpful)\b", re.IGNORECASE),
    re.compile(r"对[，,]?\s*就是这样"),
    re.compile(r"完全正确"),
    re.compile(r"正是我想要的"),
)


def extract_message_text(message: Any) -> str:
    """从消息内容中提取纯文本。"""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text_val = part.get("text")
                if isinstance(text_val, str):
                    text_parts.append(text_val)
        return " ".join(text_parts)
    return str(content)


def filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    """仅保留用户输入和最终助手响应。"""
    filtered = []
    skip_next_ai = False

    for msg in messages:
        msg_type = getattr(msg, "type", None)

        if msg_type == "human":
            content_str = extract_message_text(msg)
            if "<uploaded_files>" in content_str:
                stripped = _UPLOAD_BLOCK_RE.sub("", content_str).strip()
                if not stripped:
                    skip_next_ai = True
                    continue
                clean_msg = copy(msg)
                clean_msg.content = stripped
                filtered.append(clean_msg)
                skip_next_ai = False
            else:
                filtered.append(msg)
                skip_next_ai = False

        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                if skip_next_ai:
                    skip_next_ai = False
                    continue
                filtered.append(msg)

    return filtered


def detect_correction(messages: list[Any]) -> bool:
    """检测用户纠正信号。"""
    recent_user_msgs = [msg for msg in messages[-6:] if getattr(msg, "type", None) == "human"]

    for msg in recent_user_msgs:
        content = extract_message_text(msg).strip()
        if content and any(pattern.search(content) for pattern in _CORRECTION_PATTERNS):
            return True

    return False


def detect_reinforcement(messages: list[Any]) -> bool:
    """检测正向强化信号。"""
    recent_user_msgs = [msg for msg in messages[-6:] if getattr(msg, "type", None) == "human"]

    for msg in recent_user_msgs:
        content = extract_message_text(msg).strip()
        if content and any(pattern.search(content) for pattern in _REINFORCEMENT_PATTERNS):
            return True

    return False