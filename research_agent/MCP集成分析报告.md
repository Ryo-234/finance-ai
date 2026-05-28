# MCP (Model Context Protocol) 集成分析报告

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                   initialize_mcp_async()                          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    mcp_integration/                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │
│  │    __init__ │    │   client.py │    │    tools.py     │    │
│  │  (导出接口)  │    │ (构建参数)  │    │ (工具加载核心)  │    │
│  └─────────────┘    └─────────────┘    └─────────────────┘    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               langchain-mcp-adapters                            │
│              MultiServerMCPClient                                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MCP Servers (stdio)                             │
│           @modelcontextprotocol/server-filesystem                │
└─────────────────────────────────────────────────────────────────┘
```

## 二、核心模块说明

### 2.1 配置层 (config/mcp.py)

```python
McpConfig          # MCP全局配置（enabled, servers, interceptors）
McpServerConfig    # 单个服务器配置（command, args, env, type等）
get_mcp_config()   # 获取配置单例
```

**config.yaml 中的定义：**
```yaml
mcp:
  enabled: true
  servers:
    filesystem:
      enabled: true
      type: stdio
      command: C:/Program Files/nodejs/npx.cmd
      args: ["-y", "@modelcontextprotocol/server-filesystem", "./data"]
      description: "提供文件系统访问"
```

### 2.2 客户端参数构建 (mcp_integration/client.py)

**build_server_params()** - 为单个服务器构建参数：
```python
# stdio 传输
{"transport": "stdio", "command": "npx", "args": [...], "env": {...}}

# SSE/HTTP 传输
{"transport": "sse", "url": "https://...", "headers": {...}}
```

**build_servers_config()** - 聚合所有已启用的服务器配置

### 2.3 工具加载核心 (mcp_integration/tools.py)

```python
async def get_mcp_tools(mcp_config) -> List[BaseTool]:
    # 1. 构建服务器配置
    servers_config = build_servers_config(mcp_config)

    # 2. 创建多服务器客户端
    client = MultiServerMCPClient(servers_config, tool_name_prefix=True)

    # 3. 获取所有工具（自动转换为LangChain格式）
    tools = await client.get_tools()

    # 4. 为异步工具添加同步调用支持
    for tool in tools:
        if tool.func is None and tool.coroutine is not None:
            tool.func = _make_sync_tool_wrapper(tool.coroutine, tool.name)

    return tools
```

**关键点：** `tool_name_prefix=True` 确保不同MCP服务器的同名工具不会冲突。

## 三、工具注册流程

```
main.py 启动
    │
    ▼
initialize_mcp_async()
    │
    ▼
get_mcp_tools() ──→ MultiServerMCPClient.get_tools()
    │                         │
    │                         ▼
    │                   [BaseTool, BaseTool, ...]
    │                         │
    ▼                         ▼
get_tool_registry() ◄──── set_mcp_tools()
    │
    ▼
ToolRegistry._mcp_tools = [tools...]
```

**工具注册表 (tools/registry.py) 维护：**
```python
class ToolRegistry:
    _mcp_tools: List[BaseTool]  # MCP加载的工具

    def get_all_tools(self):
        # 返回内置工具 + MCP工具的合并列表
```

## 四、MCP在图中的调用流程

### 4.1 当前研究图结构

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│ planner  │───▶│  search  │───▶│   rag    │───▶│ synthesizer│
└──────────┘    └──────────┘    └──────────┘    └────────────┘
```

### 4.2 图节点执行

| 节点 | Agent | 工具 | 说明 |
|------|-------|------|------|
| planner | PlannerAgent | 无 | 规划任务，不调用外部工具 |
| search | SearchAgent | Tavily/DuckDuckGo | 内置搜索工具 |
| rag | RagAgent | 向量数据库 | 内置RAG工具 |
| synthesizer | SynthesizerAgent | 无 | 汇总生成，不调用外部工具 |

### 4.3 重要发现：MCP工具未被图节点调用

**当前状态：**
- MCP工具已加载到 ToolRegistry
- MCP工具可通过 `registry.get_all_tools()` 获取
- 但 **Agent 节点并未使用这些工具**

**原因分析：**
- SearchAgent/RagAgent 使用的是内置的 `community.tavily_search` 等
- 这些Agent是"专用Agent"，hardcode了特定工具
- MCP工具目前只是"可用"，但没有接入到Agent的执行流程中

## 五、如何让Agent使用MCP工具

### 方案一：改造为工具调用Agent

将当前Agent改造为使用LangChain的`create_tool_calling_agent`：

```python
from langchain.agents import create_tool_calling_agent

# 创建带工具的Agent
agent = create_tool_calling_agent(
    llm=model,
    tools=mcp_tools,  # 注入MCP工具
    prompt=system_prompt
)
```

### 方案二：新增MCP工具执行节点

在研究图中新增专门执行MCP工具的节点：

```
planner → mcp_tool_node → synthesizer
              ↑
              │
         (根据任务类型选择工具)
```

### 方案三：在Synthesizer中嵌入MCP调用

让Synthesizer在生成回答前，先调用MCP工具获取本地文件内容：

```python
async def ainvoke(self, state, ...):
    # 检查是否需要读取本地文件
    if need_local_files:
        for tool in mcp_tools:
            if tool.name == "filesystem_read_text_file":
                content = await tool.ainvoke({"path": "xxx"})
                prompt += f"\n本地文件内容：{content}"
```

## 六、数据流分析

### MCP工具加载数据流
```
config.yaml
    ↓
get_mcp_config()
    ↓
build_servers_config() → [{"filesystem": {...}}]
    ↓
MultiServerMCPClient(servers_config)
    ↓ (stdio spawn)
MCP Server Process (npx @modelcontextprotocol/server-filesystem)
    ↓ (JSON-RPC over stdio)
client.get_tools() → List[BaseTool]
    ↓
tool_registry.set_mcp_tools(tools)
```

### 工具执行数据流（stdio模式）
```
Agent.ainvoke()
    ↓
tool.func(args)  # 调用BaseTool.func
    ↓
_sync_tool_executor.submit(asyncio.run, coro)  # 线程池执行
    ↓
asyncio.run(coro)  # 新事件循环
    ↓
ClientSession.call_tool("tool_name", args)  # MCP JSON-RPC
    ↓
stdio write → MCP Server STDIN
    ↓
MCP Server 处理
    ↓
stdout read ← MCP Server STDOUT
    ↓
返回结果
```

## 七、文件清单

| 文件 | 职责 |
|------|------|
| `config/mcp.py` | MCP配置数据类定义 |
| `mcp_integration/__init__.py` | 模块导出接口 |
| `mcp_integration/client.py` | 服务器参数构建 |
| `mcp_integration/tools.py` | 工具加载核心实现 |
| `tools/registry.py` | 工具注册与管理 |
| `main.py` | MCP初始化入口 |

## 八、总结

| 方面 | 状态 | 说明 |
|------|------|------|
| MCP服务器连接 | ✅ 正常 | stdio模式连接成功 |
| 工具加载 | ✅ 正常 | 14个文件系统工具已加载 |
| 工具注册 | ✅ 正常 | 已注册到ToolRegistry |
| Agent集成 | ❌ 未完成 | Agent未使用MCP工具 |
| 工具调用 | ✅ 底层可用 | BaseTool接口正常 |

**结论：** MCP工具基础设施已完善，但需要进一步开发才能让研究Agent在执行过程中调用这些工具。当前MCP工具处于"可用但未使用"的状态。

## 九、后续优化建议

1. **短期**：在Synthesizer节点添加MCP文件读取能力，让模型能引用本地文档
2. **中期**：将Agent改造为通用工具调用架构，支持动态选择工具
3. **长期**：实现完整的MCP工具-任务匹配机制，让Planner自动决定使用哪些MCP工具
