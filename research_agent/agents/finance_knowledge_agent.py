"""金融知识整合 Agent —— 按报告模板结构组织数据。"""

import logging
from typing import Any, Dict, Optional
from pathlib import Path
import yaml

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class FinanceKnowledgeAgent(BaseAgent):
    """金融知识整合 Agent —— 按报告模板组织多源数据。

    替代原 KnowledgeAgent，核心变化：
    - 按报告模板的章节结构组织数据
    - 为每个数据点标注来源 URL 和获取时间
    - 整合金融数据源 + 网络搜索 + MCP 工具结果
    """

    def __init__(self, model=None):
        super().__init__(
            config=AgentConfig(
                name="finance_knowledge",
                description="金融知识整合 Agent - 按报告模板组织多源数据",
                model=model,
                system_prompt="""你是一个金融知识整合助手。

你的职责：
1. 将多源数据按报告模板章节结构分类
2. 标注每个数据点的来源和获取时间
3. 识别数据之间的关联和矛盾
4. 标记数据缺口（哪些章节缺少数据）""",
            )
        )

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行知识整合。"""
        state_dict = state_to_dict(state)

        if query is None:
            query = state_get(state_dict, "user_input", "")

        search_results = state_get(state_dict, "search_results", "")
        financial_data = state_get(state_dict, "financial_data", {})
        report_type = state_get(state_dict, "report_type", "company_deep")

        # 加载报告模板
        template = self._load_template(report_type)

        # 按模板章节组织数据
        organized = await self._organize_by_template(
            search_results=search_results,
            financial_data=financial_data,
            template=template,
            query=query,
        )

        return {
            **state_dict,
            "knowledge_results": organized,
            "knowledge_query": query,
        }

    def _load_template(self, report_type: str) -> dict:
        """加载报告模板。"""
        template_path = Path(__file__).parent.parent / "templates" / "reports" / f"{report_type}.yaml"
        if template_path.exists():
            with open(template_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        # 回退到默认模板
        default_path = Path(__file__).parent.parent / "templates" / "reports" / "company_deep.yaml"
        if default_path.exists():
            with open(default_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        return {"sections": []}

    async def _organize_by_template(
        self,
        search_results: str,
        financial_data: dict,
        template: dict,
        query: str,
    ) -> str:
        """按模板章节结构组织数据。

        使用 LLM 将原始数据分配到各章节，标注来源。
        """
        sections = template.get("sections", [])
        if not sections:
            return search_results

        # 构建章节结构说明
        section_descriptions = []
        for sec in sections:
            section_descriptions.append(
                f"- **{sec['title']}**（{sec.get('word_count', 300)}字）: {sec.get('prompt', '')[:100]}"
            )

        prompt = f"""请根据以下报告模板的章节结构，将原始数据整理为结构化的知识材料。

## 报告模板章节
{chr(10).join(section_descriptions)}

## 原始数据
{search_results[:3000]}

## 要求
1. 为每个章节分配相关数据
2. 标注每个数据的来源（东方财富/新浪财经/巨潮资讯/网络搜索）
3. 如果有章节缺少数据，明确标注"数据待补充"
4. 识别数据之间的关联（如：某新闻对某财务指标的影响）

请以 Markdown 格式输出，每个章节作为二级标题。
"""

        try:
            response = await self.model.ainvoke([
                SystemMessage(content=self.config.system_prompt),
                HumanMessage(content=prompt),
            ])
            return response.content
        except Exception as e:
            logger.warning(f"知识整合 LLM 调用失败: {e}")
            # 降级：直接返回原始搜索结果
            return f"## 原始数据\n\n{search_results[:2000]}\n\n> 注意：知识整合步骤跳过，数据未按章节组织。"
