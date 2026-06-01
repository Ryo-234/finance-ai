"""标题生成中间件 —— 首轮对话完成后自动用 LLM 生成会话标题。

参考 DeerFlow 的 TitleMiddleware 设计模式。
触发条件：title 为空、只有1条用户消息、至少有1条 AI 回复。
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from middleware.base import BaseMiddleware, MiddlewareResult
from config.models import create_chat_model

logger = logging.getLogger(__name__)

# 回退标题生成用的最大截取字符数
_DEFAULT_MAX_CHARS = 30
_FALLBACK_MAX_CHARS = 20


def _clean_title(raw: str, max_chars: int) -> str:
    """清洗 LLM 生成的标题：去引号、去句号、去 think 标签、截断。

    参数：
        raw: LLM 原始输出
        max_chars: 最大字符数

    返回：
        清洗后的标题字符串
    """
    import re

    # 去除 <think>...</think> 块
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw)

    # 去除首尾空白、引号、句号
    result = raw.strip().strip('"\'').strip("。").strip("，").strip("“”")

    # 只取第一行
    result = result.split("\n")[0].strip()

    # 截断
    if len(result) > max_chars:
        result = result[:max_chars]

    return result


class TitleMiddleware(BaseMiddleware):
    """标题生成中间件。

    设计模式（参考 DeerFlow TitleMiddleware）：
    - 挂载到 after_model 钩子
    - 只在首轮对话完成后触发一次
    - 调用 LLM 生成简洁标题
    - LLM 失败时回退到用户消息截断

    配置参数：
    - enabled: 是否启用
    - order: 执行顺序（after_model 阶段）
    - max_chars: 标题最大字符数（默认 30）
    """

    name: str = "title"
    description: str = "首轮对话后自动生成会话标题"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 30,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ):
        """初始化标题中间件。

        参数：
            enabled: 是否启用
            order: 在中间件链中的执行顺序
            max_chars: 标题最大字符数
        """
        super().__init__(enabled=enabled, order=order)
        self.max_chars = max_chars

    def _fallback_title(self, message: HumanMessage) -> str:
        """LLM 调用失败时的回退方案：取用户消息前 N 个字符。

        参数：
            message: 用户消息

        返回：
            截断后的标题文本
        """
        content = message.content
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        text = str(content).strip()
        if len(text) > _FALLBACK_MAX_CHARS:
            text = text[:_FALLBACK_MAX_CHARS] + "..."
        return text

    async def _generate_title(
        self,
        user_msg: HumanMessage,
        ai_msg: AIMessage,
    ) -> str:
        """调用 LLM 生成会话标题。

        参数：
            user_msg: 用户消息
            ai_msg: AI 回复

        返回：
            生成的标题字符串
        """
        # 提取文本内容
        user_text = str(user_msg.content if isinstance(user_msg.content, str) else user_msg.content)
        ai_text = str(ai_msg.content if isinstance(ai_msg.content, str) else ai_msg.content)

        # 截取前 500 字符作为上下文
        user_text = user_text[:500]
        ai_text = ai_text[:500]

        prompt = (
            f"根据以下对话，生成一个简短的会话标题（不超过15个字）。\n"
            f"只输出标题文本，不要加引号、标点或任何前缀。\n\n"
            f"用户: {user_text}\n"
            f"助手: {ai_text}\n\n"
            f"标题:"
        )

        try:
            model = create_chat_model()
            response = await model.ainvoke([HumanMessage(content=prompt)])
            title = _clean_title(str(response.content), self.max_chars)
            if title:
                return title
        except Exception as e:
            logger.warning(f"标题生成失败，使用回退方案: {e}")

        # 回退：用户消息截断
        return self._fallback_title(user_msg)

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """after_model：委托给 _check_and_generate。"""
        return await self._check_and_generate(state, runtime)

    async def after_agent(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """after_agent：兜底路径。

        对于问候/澄清等不经过合成节点的意图，after_model 不会触发。
        用 after_agent 确保标题在所有路径都能生成。
        """
        return await self._check_and_generate(state, runtime)

    async def _check_and_generate(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """检查是否需要生成标题（首轮对话完成后触发一次）。

        触发条件：
        1. 状态中没有 title
        2. 只有 1 条用户消息（首轮对话）
        3. 至少有 1 条 AI 回复（对话已完成至少一次来回）
        4. 有 answer 或 final_answer（已生成回复）
        """
        # 已有标题则跳过
        if state.get("title"):
            return None

        # 确认已生成有效回复
        answer = state.get("answer") or state.get("final_answer") or state.get("greeting_response") or ""
        if not answer:
            return None

        messages = state.get("messages", [])
        user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
        ai_msgs = [m for m in messages if isinstance(m, AIMessage)]

        # 不是首轮对话
        if len(user_msgs) < 1:
            return None

        # 还没有回复（无 AI 消息且回答为空）
        if len(ai_msgs) < 1 and not answer:
            return None

        thread_id = runtime.get("thread_id", "unknown")
        logger.info("开始为会话 %s 生成标题...", thread_id)

        # 以用户消息为上下文，用 LLM 回答生成标题
        # 如果无 AIMessage，用 answer 文本作为 AI 上下文
        user_context = str(user_msgs[0].content)[:500]
        ai_context = str(ai_msgs[-1].content)[:500] if ai_msgs else answer[:500]

        # 手动构建标题（绕过 _generate_title 的 HumanMessage/AIMessage 要求）
        prompt = (
            f"根据以下对话，生成一个简短的会话标题（不超过15个字）。\n"
            f"只输出标题文本，不要加引号、标点或任何前缀。\n\n"
            f"用户: {user_context}\n"
            f"助手: {ai_context}\n\n"
            f"标题:"
        )

        try:
            model = create_chat_model()
            response = await model.ainvoke([HumanMessage(content=prompt)])
            title = _clean_title(str(response.content), self.max_chars)
        except Exception as e:
            logger.warning(f"标题生成失败，使用回退方案: {e}")
            title = str(user_context)[:_FALLBACK_MAX_CHARS].strip() + "..."

        if not title:
            title = str(user_context)[:_FALLBACK_MAX_CHARS].strip() + "..."

        logger.info("会话 %s 标题已生成: %s", thread_id, title)

        return MiddlewareResult.updated({"title": title})
