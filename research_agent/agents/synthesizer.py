"""汇总 Agent - 整合结果生成最终回答。"""

from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


class SynthesizerAgent(BaseAgent):
    """汇总 Agent - 整合多个来源的信息生成最终回答。

    功能：
    1. 整合搜索结果和 RAG 结果
    2. 去除冗余和冲突信息
    3. 生成结构化、完整的回答
    """

    def __init__(self, model=None):
        """初始化汇总 Agent。"""
        super().__init__(
            config=AgentConfig(
                name="synthesizer",
                description="汇总 Agent - 整合信息生成最终回答",
                model=model,
                system_prompt="""你是一个专业的研究报告生成助手。

你的职责：
1. 整合来自多个来源的信息（搜索结果、知识库等）
2. 去除冗余信息，处理冲突
3. 生成结构清晰、内容完整的回答
4. 注明信息来源，确保可追溯性

重要原则：
1. **日期准确性**：如果搜索结果中没有明确标注日期，不要凭空编造日期。只写"根据搜索结果"或"据报道"，不要写具体的年月日。
2. **实事求是的语气**：不确定的信息要明确说明，不要推测。
3. **禁止编造**：如果搜索结果确实没有今天的新闻，明确告知用户"搜索结果未明确显示今日信息"，不要自行推断日期。
4. **引用搜索结果中的原始日期**：如果搜索结果网页上有具体日期，引用该日期。

输出格式：
- 使用清晰的标题和层次结构
- 适当使用列表和表格
- 关键信息注明来源（URL）
- 保持专业、客观的语气
- 如果搜索结果中无明确日期，在回答开头说明"以下信息整理自网络搜索结果，日期以各来源网站标注为准" """,
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        user_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成最终回答。"""
        # 统一转换为字典
        state_dict = state_to_dict(state)

        if user_input is None:
            user_input = state_get(state_dict, "user_input", "")

        # 收集所有结果
        search_results = state_get(state_dict, "search_results", "")
        rag_results = state_get(state_dict, "rag_results", "")
        memory_context = state_get(state_dict, "memory_context", "")

        # 构建综合提示词
        prompt = self._build_synthesis_prompt(
            user_input=user_input,
            search_results=search_results,
            rag_results=rag_results,
            memory_context=memory_context,
        )

        # 调用模型生成回答
        response = await self.model.ainvoke([
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=prompt),
        ])

        return {
            **state_dict,
            "final_answer": response.content,
            "sources": self._extract_sources(search_results, rag_results),
        }

    def _build_synthesis_prompt(
        self,
        user_input: str,
        search_results: str,
        rag_results: str,
        memory_context: str,
    ) -> str:
        """构建综合提示词。"""
        import datetime
        today = datetime.datetime.now().strftime("%Y年%m月%d日")

        prompt_parts = [
            f"【重要】今天是 {today}，请根据这个日期来判断搜索结果中的信息时效性。\n",
            f"原始问题：{user_input}\n",
        ]

        if search_results:
            prompt_parts.append(f"=== 网络搜索结果 ===\n{search_results}\n")

        if rag_results:
            prompt_parts.append(f"=== 知识库检索结果 ===\n{rag_results}\n")

        if memory_context:
            prompt_parts.append(f"=== 相关记忆上下文 ===\n{memory_context}\n")

        prompt_parts.append(
            "请基于以上信息，生成一个完整、准确的回答。\n\n"
            "【硬性要求】\n"
            "1. 如果搜索结果中各网页有标注日期，以搜索结果中的日期为准\n"
            "2. 如果搜索结果中没有明确日期，**绝对不要编造具体日期**，只写'根据搜索结果'或'据报道'\n"
            "3. 回答中不要出现'2024年'、'2023年'等具体年份除非搜索结果中明确提到\n"
            "4. 注明信息来源（URL）\n"
            "5. 如有信息冲突，说明并提供多种观点"
        )

        return "\n".join(prompt_parts)

    def _extract_sources(self, search_results: str, rag_results: str) -> list:
        """提取信息来源列表。"""
        sources = []

        # 从搜索结果中提取 URL
        if search_results:
            import re
            urls = re.findall(r"URL: (https?://[^\s]+)", search_results)
            sources.extend([{"type": "web", "url": url} for url in urls])

        # 从 RAG 结果中提取来源
        if rag_results:
            import re
            source_matches = re.findall(r"来源: ([^\n]+)", rag_results)
            sources.extend([{"type": "knowledge_base", "source": src} for src in source_matches])

        return sources