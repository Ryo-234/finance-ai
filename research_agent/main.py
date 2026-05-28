"""Research Agent - 智能研究助手入口。"""

import asyncio
import logging
import os
import sys
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph.research_graph import run_research, set_middleware_manager
from memory import get_memory_data, update_memory_from_conversation
from memory.prompt import format_memory_for_injection
from mcp_integration import get_mcp_tools, get_mcp_config
from tools.registry import get_tool_registry
from middleware.factory import get_default_middleware_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def initialize_mcp_async() -> None:
    """异步初始化 MCP 工具。"""
    try:
        mcp_config = get_mcp_config()
        if not mcp_config.enabled:
            logger.info("MCP 功能已禁用")
            return

        # 检查是否有启用的服务器
        enabled_servers = [s for s, cfg in mcp_config.servers.items() if cfg.enabled]
        if not enabled_servers:
            logger.info("没有已启用的 MCP 服务器")
            return

        logger.info(f"正在初始化 {len(enabled_servers)} 个 MCP 服务器: {enabled_servers}")

        # 加载 MCP 工具
        mcp_tools = await get_mcp_tools(mcp_config)

        if mcp_tools:
            # 注册到工具注册表
            registry = get_tool_registry()
            registry.set_mcp_tools(mcp_tools)
            logger.info(f"成功加载 {len(mcp_tools)} 个 MCP 工具")
        else:
            logger.info("未加载任何 MCP 工具")

    except Exception as e:
        logger.warning(f"MCP 初始化失败: {e}")


async def main():
    """主函数。"""
    print("=" * 60)
    print("Research Agent - 智能研究助手")
    print("=" * 60)
    print()

    # 初始化 MCP
    await initialize_mcp_async()
    print()

    # 初始化中间件系统
    middleware_manager = get_default_middleware_manager()
    set_middleware_manager(middleware_manager)
    print("中间件系统已初始化:")
    for mw_info in middleware_manager.list_middlewares():
        status = "启用" if mw_info["enabled"] else "禁用"
        print(f"  - {mw_info['name']}: {status}")
    print()

    # 检查 API Key
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("警告：未设置 DASHSCOPE_API_KEY 环境变量")
        print("请设置：export DASHSCOPE_API_KEY='your-api-key'")
        print()

    # 交互式循环
    while True:
        try:
            user_input = input("请输入您的问题（输入 'quit' 退出）: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("感谢使用 Research Agent！")
                break

            if user_input.lower() == "memory":
                # 显示当前记忆
                memory_data = get_memory_data()
                print("\n当前记忆：")
                print(format_memory_for_injection(memory_data, max_tokens=1000))
                print()
                continue

            if user_input.lower() == "mcp":
                # 显示 MCP 状态
                registry = get_tool_registry()
                mcp_tools = registry.get_mcp_tools()
                mcp_config = get_mcp_config()
                print("\nMCP 状态：")
                print(f"  MCP 功能: {'启用' if mcp_config.enabled else '禁用'}")
                print(f"  已启用服务器: {sum(1 for c in mcp_config.servers.values() if c.enabled)}")
                print(f"  已加载工具: {len(mcp_tools)}")
                if mcp_tools:
                    print("\n可用 MCP 工具：")
                    for tool in mcp_tools:
                        print(f"  - {tool.name}")
                print()
                continue

            if user_input.lower() == "middleware":
                # 显示中间件状态
                middleware_manager = get_default_middleware_manager()
                print("\n中间件状态：")
                print(f"  已启用: {middleware_manager.enabled_count} 个")
                for mw_info in middleware_manager.list_middlewares():
                    print(f"  - {mw_info['name']}: {mw_info['description']}")
                print()
                continue

            print("\n正在分析您的问题...")
            print()

            # 运行研究流程
            result = await run_research(user_input)

            # 显示结果
            print("\n" + "=" * 60)
            print("回答：")
            print("=" * 60)
            print(result.get("answer", "抱歉，未能生成回答"))
            print()

            # 显示来源
            sources = result.get("sources", [])
            if sources:
                print("-" * 60)
                print("信息来源：")
                for i, source in enumerate(sources, 1):
                    source_type = source.get("type", "unknown")
                    if source_type == "web":
                        print(f"  [{i}] {source.get('url', 'N/A')}")
                    else:
                        print(f"  [{i}] {source.get('source', 'N/A')}")
                print()

            # 显示任务执行情况
            tasks = result.get("tasks", [])
            if tasks:
                print("-" * 60)
                print("执行的任务：")
                for task in tasks:
                    status = task.get("status", "unknown")
                    task_type = task.get("task_type", "unknown")
                    desc = task.get("description", "")[:50]
                    print(f"  - [{status}] {task_type}: {desc}...")
                print()

        except KeyboardInterrupt:
            print("\n\n已中断，正在退出...")
            break
        except Exception as e:
            print(f"\n错误：{str(e)}\n")


def chat(message: str) -> dict:
    """同步聊天接口。"""
    return asyncio.run(run_research(message))


if __name__ == "__main__":
    asyncio.run(main())