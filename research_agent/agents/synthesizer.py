"""汇总 Agent - 整合结果生成最终回答。"""

import logging
from typing import Any, Dict, Optional

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = logging.getLogger(__name__)


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
        viewed_images = state_get(state_dict, "viewed_images", {})
        messages = state_get(state_dict, "messages", [])

        # 检查是否有图片需要处理
        # 优先使用 viewed_images，如果为空则从消息中提取
        has_images = bool(viewed_images)
        extracted_images = {}

        if not has_images and messages:
            # viewed_images 为空，尝试从消息中提取图片
            extracted_images = self._extract_images_from_messages(messages)
            has_images = bool(extracted_images)
            if has_images:
                logger.info(f"从消息中提取了 {len(extracted_images)} 张图片")

        if has_images:
            # 有图片：使用视觉模型，直接构建包含图片的消息
            vision_model = self._get_vision_model()
            # 优先使用 viewed_images，如果为空则使用 extracted_images
            images_to_use = viewed_images if viewed_images else extracted_images
            messages = self._build_vision_messages(
                user_input=user_input,
                search_results=search_results,
                rag_results=rag_results,
                memory_context=memory_context,
                viewed_images=images_to_use,
            )
            response = await vision_model.ainvoke(messages)
        else:
            # 无图片：使用普通文本模型
            prompt = self._build_synthesis_prompt(
                user_input=user_input,
                search_results=search_results,
                rag_results=rag_results,
                memory_context=memory_context,
            )
            response = await self.model.ainvoke([
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=prompt),
            ])

        return {
            **state_dict,
            "final_answer": response.content,
            "sources": self._extract_sources(search_results, rag_results),
        }

    def _build_vision_messages(
        self,
        user_input: str,
        search_results: str,
        rag_results: str,
        memory_context: str,
        viewed_images: dict,
    ) -> list:
        """构建包含图片的混合内容消息（用于视觉模型）。"""
        import datetime
        today = datetime.datetime.now().strftime("%Y年%m月%d日")

        # 构建用户消息的混合内容
        user_content = []

        # 添加文本部分
        text_parts = [
            f"【重要】今天是 {today}，请根据这个日期来判断搜索结果中的信息时效性。\n",
            f"原始问题：{user_input}\n",
        ]

        # 添加图片
        if viewed_images:
            text_parts.append("=== 用户上传的图片 ===\n")
            for path, data in viewed_images.items():
                mime_type = data.get("mime_type", "image/jpeg")
                text_parts.append(f"图片: {path} (MIME: {mime_type})\n")

        if search_results:
            text_parts.append(f"=== 网络搜索结果 ===\n{search_results}\n")

        if rag_results:
            text_parts.append(f"=== 知识库检索结果 ===\n{rag_results}\n")

        if memory_context:
            text_parts.append(f"=== 相关记忆上下文 ===\n{memory_context}\n")

        text_parts.append(
            "请基于以上信息，生成一个完整、准确的回答。\n\n"
            "【硬性要求】\n"
            "1. 如果搜索结果中各网页有标注日期，以搜索结果中的日期为准\n"
            "2. 如果搜索结果中没有明确日期，**绝对不要编造具体日期**，只写'根据搜索结果'或'据报道'\n"
            "3. 回答中不要出现'2024年'、'2023年'等具体年份除非搜索结果中明确提到\n"
            "4. 注明信息来源（URL）\n"
            "5. 如有信息冲突，说明并提供多种观点"
        )

        user_content.append({"type": "text", "text": "\n".join(text_parts)})

        # 添加图片数据
        for path, data in viewed_images.items():
            mime_type = data.get("mime_type", "image/jpeg")
            base64_data = data.get("base64", "")
            if base64_data:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
                })

        return [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=user_content),
        ]

    def _get_vision_model(self):
        """获取视觉模型实例。"""
        from config.vision import create_vision_model
        return create_vision_model()

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

    def _extract_images_from_messages(self, messages: list) -> dict:
        """从消息中提取图片数据。

        当 viewed_images 为空时，尝试从已注入的消息中提取图片。

        Returns:
            dict: {path: {base64: str, mime_type: str}}
        """
        extracted = {}

        for msg in messages:
            if not isinstance(msg, HumanMessage):
                continue

            content = msg.content
            if not isinstance(content, list):
                continue

            # 检查是否包含图片注入标记
            has_image_injection = False
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if "以下是你已读取的图片" in text:
                        has_image_injection = True
                        break

            if not has_image_injection:
                continue

            # 提取图片数据
            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "image_url":
                    image_url = block.get("image_url", {})
                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        if url.startswith("data:"):
                            # 解析 data URL
                            # 格式: data:mime_type;base64,data
                            try:
                                header, data_part = url.split(",", 1)
                                mime_part = header.replace("data:", "")
                                if ";base64" in mime_part:
                                    mime_type = mime_part.replace(";base64", "")
                                else:
                                    mime_type = mime_type or "image/jpeg"
                                base64_data = data_part

                                # 使用路径作为 key（从之前的文本块中提取）
                                path = f"extracted_image_{len(extracted)}"
                                extracted[path] = {
                                    "base64": base64_data,
                                    "mime_type": mime_type,
                                }
                            except Exception:
                                continue

        return extracted