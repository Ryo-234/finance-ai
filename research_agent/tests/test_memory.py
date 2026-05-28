"""Memory 系统测试。"""

import pytest
import asyncio
from memory.storage import FileMemoryStorage, create_empty_memory
from memory.queue import MemoryUpdateQueue
from memory.updater import MemoryUpdater


class TestMemoryStorage:
    """测试记忆存储。"""

    def test_create_empty_memory(self):
        """测试创建空记忆。"""
        memory = create_empty_memory()
        assert memory["version"] == "1.0"
        assert "user" in memory
        assert "history" in memory
        assert "facts" in memory

    def test_storage_save_load(self, tmp_path):
        """测试存储保存和加载。"""
        storage = FileMemoryStorage(base_dir=str(tmp_path))

        test_memory = create_empty_memory()
        test_memory["user"]["workContext"]["summary"] = "测试工作上下文"

        success = storage.save(test_memory, user_id="test_user")
        assert success

        loaded = storage.load(user_id="test_user")
        assert loaded["user"]["workContext"]["summary"] == "测试工作上下文"

    def test_storage_nonexistent_user(self, tmp_path):
        """测试加载不存在的用户记忆。"""
        storage = FileMemoryStorage(base_dir=str(tmp_path))

        memory = storage.load(user_id="nonexistent")
        assert memory["version"] == "1.0"


class TestMemoryQueue:
    """测试记忆更新队列。"""

    def test_queue_initialization(self):
        """测试队列初始化。"""
        queue = MemoryUpdateQueue(debounce_seconds=10)
        assert queue.debounce_seconds == 10
        assert queue.pending_count == 0

    def test_queue_add(self):
        """测试添加对话到队列。"""
        queue = MemoryUpdateQueue()

        class MockMessage:
            def __init__(self, content):
                self.type = "human"
                self.content = content

        messages = [MockMessage("测试消息")]
        queue.add("thread_1", messages, user_id="user_1")

        assert queue.pending_count == 1

    def test_queue_clear(self):
        """测试清空队列。"""
        queue = MemoryUpdateQueue()

        class MockMessage:
            def __init__(self, content):
                self.type = "human"
                self.content = content

        queue.add("thread_1", [MockMessage("测试")], user_id="user_1")
        assert queue.pending_count == 1

        queue.clear()
        assert queue.pending_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])