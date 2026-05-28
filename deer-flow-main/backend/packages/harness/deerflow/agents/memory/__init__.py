"""DeerFlow 的 Memory（记忆系统）模块。

本模块提供全局记忆机制，具备以下功能：
- 将用户上下文和对话历史存储在 memory.json 中
- 使用 LLM 从对话中总结并提取事实
- 将相关记忆注入到系统提示词中，实现个性化响应
"""

from deerflow.agents.memory.prompt import (
    FACT_EXTRACTION_PROMPT,
    MEMORY_UPDATE_PROMPT,
    format_conversation_for_update,
    format_memory_for_injection,
)
from deerflow.agents.memory.queue import (
    ConversationContext,
    MemoryUpdateQueue,
    get_memory_queue,
    reset_memory_queue,
)
from deerflow.agents.memory.storage import (
    FileMemoryStorage,
    MemoryStorage,
    get_memory_storage,
)
from deerflow.agents.memory.updater import (
    MemoryUpdater,
    clear_memory_data,
    delete_memory_fact,
    get_memory_data,
    reload_memory_data,
    update_memory_from_conversation,
)

__all__ = [
    # 提示词工具
    "MEMORY_UPDATE_PROMPT",
    "FACT_EXTRACTION_PROMPT",
    "format_memory_for_injection",
    "format_conversation_for_update",
    # 队列
    "ConversationContext",
    "MemoryUpdateQueue",
    "get_memory_queue",
    "reset_memory_queue",
    # 存储
    "MemoryStorage",
    "FileMemoryStorage",
    "get_memory_storage",
    # 更新器
    "MemoryUpdater",
    "clear_memory_data",
    "delete_memory_fact",
    "get_memory_data",
    "reload_memory_data",
    "update_memory_from_conversation",
]