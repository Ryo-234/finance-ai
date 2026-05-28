"""Agent 系统测试。"""

import pytest
from agents.base import BaseAgent, AgentConfig
from agents.planner import PlannerAgent
from agents.search_agent import SearchAgent
from agents.knowledge_agent import KnowledgeAgent
from agents.synthesizer import SynthesizerAgent


class TestBaseAgent:
    """测试 Agent 基类。"""

    def test_agent_config(self):
        """测试 Agent 配置。"""
        config = AgentConfig(
            name="test_agent",
            description="测试 Agent",
            temperature=0.5,
        )

        assert config.name == "test_agent"
        assert config.description == "测试 Agent"
        assert config.temperature == 0.5


class TestPlannerAgent:
    """测试规划 Agent。"""

    @pytest.mark.asyncio
    async def test_planner_analyze(self):
        """测试规划 Agent 分析功能。"""
        planner = PlannerAgent()

        state = {"user_input": "什么是人工智能？"}
        result = await planner.ainvoke(state)

        assert "tasks" in result
        assert len(result["tasks"]) > 0


class TestSearchAgent:
    """测试搜索 Agent。"""

    def test_search_agent_init(self):
        """测试搜索 Agent 初始化。"""
        agent = SearchAgent(provider="tavily")
        assert agent.provider == "tavily"
        assert agent.name == "search"


class TestKnowledgeAgent:
    """测试知识库 Agent。"""

    def test_knowledge_agent_init(self):
        """测试知识库 Agent 初始化。"""
        agent = KnowledgeAgent()
        assert agent.name == "knowledge"


class TestSynthesizerAgent:
    """测试汇总 Agent。"""

    def test_synthesizer_init(self):
        """测试汇总 Agent 初始化。"""
        agent = SynthesizerAgent()
        assert agent.name == "synthesizer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])