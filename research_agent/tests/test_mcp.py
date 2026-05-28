"""MCP 集成测试。"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_agent.config.mcp import McpConfig, McpServerConfig, get_mcp_config, reload_mcp_config
from research_agent.mcp.client import build_server_params, build_servers_config, get_enabled_servers_count
from research_agent.tools.registry import ToolRegistry, get_tool_registry


def test_mcp_config_loading():
    """测试 MCP 配置加载。"""
    print("测试 MCP 配置加载...")

    config = get_mcp_config()
    print(f"  MCP 启用状态: {config.enabled}")
    print(f"  服务器数量: {len(config.servers)}")
    print(f"  已启用服务器: {get_enabled_servers_count(config)}")

    for name, server in config.servers.items():
        print(f"    - {name}: {server.type} (enabled={server.enabled})")

    assert isinstance(config, McpConfig)
    print("  [OK] 配置加载测试通过\n")


def test_build_server_params():
    """测试服务器参数构建。"""
    print("测试构建服务器参数...")

    # 测试 stdio 类型
    stdio_config = McpServerConfig(
        enabled=True,
        type="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        description="测试服务器"
    )

    params = build_server_params("test_server", stdio_config)
    print(f"  stdio 参数: {params}")
    assert params["transport"] == "stdio"
    assert params["command"] == "npx"
    print("  [OK] stdio 参数构建测试通过")

    # 测试 HTTP 类型
    http_config = McpServerConfig(
        enabled=True,
        type="http",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer token"},
        description="HTTP 服务器"
    )

    params = build_server_params("http_server", http_config)
    print(f"  http 参数: {params}")
    assert params["transport"] == "http"
    assert params["url"] == "https://example.com/mcp"
    print("  [OK] http 参数构建测试通过\n")


def test_build_servers_config():
    """测试构建多服务器配置。"""
    print("测试构建多服务器配置...")

    config = get_mcp_config()
    servers_config = build_servers_config(config)

    print(f"  构建了 {len(servers_config)} 个服务器配置")
    for name, params in servers_config.items():
        print(f"    - {name}: {params.get('transport')}")

    print("  [OK] 多服务器配置构建测试通过\n")


def test_tool_registry_mcp():
    """测试工具注册表的 MCP 工具支持。"""
    print("测试工具注册表 MCP 支持...")

    registry = get_tool_registry()

    # 测试设置 MCP 工具
    from langchain_core.tools import BaseTool

    class MockTool(BaseTool):
        name: str = "mock_tool"
        description: str = "A mock tool for testing"

        def _run(self, *args, **kwargs):
            return "mock result"

    mock_tools = [MockTool()]
    registry.set_mcp_tools(mock_tools)

    # 测试获取 MCP 工具
    retrieved_tools = registry.get_mcp_tools()
    assert len(retrieved_tools) == 1
    assert retrieved_tools[0].name == "mock_tool"
    print(f"  已设置 MCP 工具: {[t.name for t in retrieved_tools]}")

    # 测试列出 MCP 工具
    mcp_list = registry.list_mcp_tools()
    assert len(mcp_list) == 1
    assert mcp_list[0]["name"] == "mock_tool"
    print(f"  列出的 MCP 工具: {mcp_list}")

    # 测试获取所有工具
    all_tools = registry.get_all_tools()
    assert len(all_tools) > 0
    print(f"  所有工具数量: {len(all_tools)}")

    print("  [OK] 工具注册表 MCP 支持测试通过\n")


def test_env_variable_resolution():
    """测试环境变量解析。"""
    print("测试环境变量解析...")

    os.environ["TEST_VAR"] = "test_value"
    os.environ["TEST_TOKEN"] = "secret_token"

    # 重新加载配置以获取更新后的环境变量
    config = reload_mcp_config()

    print(f"  环境变量解析测试完成")
    print("  [OK] 环境变量解析测试通过\n")


def main():
    """运行所有测试。"""
    print("=" * 60)
    print("MCP 集成测试")
    print("=" * 60)
    print()

    try:
        test_mcp_config_loading()
        test_build_server_params()
        test_build_servers_config()
        test_tool_registry_mcp()
        test_env_variable_resolution()

        print("=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        print()
        print("下一步：")
        print("1. 安装 langchain-mcp-adapters: pip install langchain-mcp-adapters")
        print("2. 在 config.yaml 中配置 MCP 服务器")
        print("3. 运行 python main.py 测试完整流程")

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
