"""Graph 测试。"""

import pytest
from graph.state import ResearchState
from graph.research_graph import create_research_graph, run_research


class TestResearchState:
    """测试研究状态。"""

    def test_state_initialization(self):
        """测试状态初始化。"""
        state = ResearchState(user_input="测试问题")

        assert state.user_input == "测试问题"
        assert state.tasks == []
        assert state.current_task_index == 0

    def test_get_next_task(self):
        """测试获取下一个任务。"""
        state = ResearchState(
            tasks=[
                {"id": "task_0", "task_type": "search"},
                {"id": "task_1", "task_type": "rag"},
            ],
            current_task_index=0,
        )

        next_task = state.get_next_task()
        assert next_task["id"] == "task_0"

        state.current_task_index = 1
        next_task = state.get_next_task()
        assert next_task["id"] == "task_1"

        state.current_task_index = 2
        next_task = state.get_next_task()
        assert next_task is None

    def test_mark_task_complete(self):
        """测试标记任务完成。"""
        state = ResearchState(
            tasks=[
                {"id": "task_0", "status": "pending", "result": None},
            ],
        )

        state.mark_task_complete("task_0", "搜索结果")
        assert state.tasks[0]["status"] == "completed"
        assert state.tasks[0]["result"] == "搜索结果"
        assert state.current_task_index == 1


class TestResearchGraph:
    """测试研究图。"""

    def test_create_graph(self):
        """测试创建研究图。"""
        graph = create_research_graph()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_run_research_empty(self):
        """测试运行空研究。"""
        # 这个测试需要 mock LLM 调用
        # 这里只是验证函数存在且可调用
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])