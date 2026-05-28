# DeerFlow 项目分析报告

> 分析时间: 2026-05-10  
> 项目源码: https://github.com/bytedance/deer-flow

---

## 一、项目概述

**DeerFlow** (Deep Exploration and Efficient Research Flow) 是由字节跳动开发的**开源超级 Agent 框架**，基于 LangGraph 和 LangChain 构建。它从深度研究框架演变为"超级 Agent 工具箱"，支持子 Agent 编排、持久化记忆、沙箱执行和可扩展技能系统。

### 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.12+ / FastAPI / LangGraph / LangChain |
| **前端** | Next.js 16+ / React 19 / TypeScript / Tailwind CSS |
| **部署** | Docker / Nginx 反向代理 |

### 项目定位

- **定位**: 展示技术深度的实习预备项目 / GitHub 开源项目
- **特点**: 模块化设计、企业级架构、大量可复用组件

---

## 二、项目架构

### 目录结构

```
deer-flow/
├── backend/                    # 后端应用
│   ├── app/
│   │   ├── gateway/           # FastAPI 网关 API (端口 8001)
│   │   │   ├── routers/       # 路由模块 (threads, runs, models, skills, mcp 等)
│   │   │   └── auth/          # 认证系统 (JWT/SQLite)
│   │   └── channels/          # IM 渠道集成 (Telegram, Slack, Feishu, WeChat, WeCom)
│   ├── packages/harness/      # 核心 Agent 框架 (deerflow-harness)
│   │   └── deerflow/
│   │       ├── agents/        # Agent 系统 (lead_agent, middlewares, memory)
│   │       ├── sandbox/       # 沙箱执行系统 (local/docker)
│   │       ├── subagents/     # 子 Agent 委托系统
│   │       ├── tools/         # 工具集 (bash, file, view_image 等)
│   │       ├── models/        # 模型工厂 (OpenAI, vLLM, Claude 等)
│   │       ├── skills/        # 技能系统
│   │       ├── mcp/           # MCP 服务器集成
│   │       └── community/     # 社区工具 (tavily, firecrawl, image_search)
│   ├── docs/                  # 文档
│   └── tests/                 # 测试套件
├── frontend/                   # Next.js 前端 (端口 3000)
│   └── src/
├── skills/                     # Agent 技能目录
│   ├── public/                # 内置技能 (research, report-generation 等)
│   └── custom/                # 自定义技能
├── docker/                     # Docker 配置
└── config.yaml                 # 主配置文件
```

### 核心模块详解

#### 1. Agent 系统 (`deerflow/agents/`)

| 模块 | 功能 |
|------|------|
| `lead_agent/` | 主 Agent 工厂 + 系统提示生成 |
| `middlewares/` | 18 个中间件链 (线程数据、沙箱、错误处理、摘要、待办事项等) |
| `memory/` | LLM 驱动的持久化记忆系统 |
| `thread_state.py` | ThreadState 数据结构定义 |

**中间件执行顺序**:
```
ThreadDataMiddleware → UploadsMiddleware → SandboxMiddleware → 
DanglingToolCallMiddleware → LLMErrorHandlingMiddleware → GuardrailMiddleware →
SandboxAuditMiddleware → ToolErrorHandlingMiddleware → SummarizationMiddleware →
TodoListMiddleware → TokenUsageMiddleware → TitleMiddleware → MemoryMiddleware →
ViewImageMiddleware → DeferredToolFilterMiddleware → SubagentLimitMiddleware →
LoopDetectionMiddleware → ClarificationMiddleware (最后)
```

#### 2. 沙箱系统 (`deerflow/sandbox/`)

| 模式 | 说明 |
|------|------|
| `LocalSandboxProvider` | 本地文件系统执行 (单例模式) |
| `AioSandboxProvider` | Docker 隔离容器执行 |

**虚拟路径映射**:
- Agent 视角: `/mnt/user-data/{workspace,uploads,outputs}`
- 实际路径: `backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/...`

#### 3. 子 Agent 系统 (`deerflow/subagents/`)

- **内置 Agent**: 通用 Agent (所有工具)、Bash Agent (命令专家)
- **并发控制**: 最多 3 个并发子 Agent
- **超时**: 15 分钟
- **工作流程**: `task()` 工具 → SubagentExecutor → 后台线程 → SSE 事件 → 结果聚合

#### 4. 技能系统 (`deerflow/skills/`)

- **格式**: 目录结构 + `SKILL.md` (YAML 元数据)
- **加载**: 按需渐进式加载，不预加载全部
- **安装**: 支持 `.skill` 压缩包安装

#### 5. MCP 系统 (`deerflow/mcp/`)

- 使用 `langchain-mcp-adapters` 管理多服务器
- **传输方式**: stdio、SSE、HTTP
- **OAuth 支持**: client_credentials、refresh_token 自动刷新
- **缓存**: 基于 mtime 的自动失效

---

## 三、后端 Memory 架构详解

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Agent Execution Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌──────────┐    ┌────────────────────┐    ┌──────────────────────────┐   │
│   │  User    │───▶│  MemoryMiddleware  │───▶│   Other Middlewares...   │   │
│   │  Input   │    │  (after_agent)      │    │                          │   │
│   └──────────┘    └────────┬───────────┘    └──────────────────────────┘   │
│                           │                                              │
│                           ▼                                              │
│                    ┌──────────────┐                                       │
│                    │   Queue      │  ◀── debounce (默认30秒)              │
│                    │   (内存)      │                                       │
│                    └──────┬───────┘                                       │
│                           │ (定时触发)                                     │
│                           ▼                                              │
│                    ┌──────────────┐                                       │
│                    │  Updater     │  ◀── LLM 调用                         │
│                    │  (后台线程)   │                                       │
│                    └──────┬───────┘                                       │
│                           │                                              │
│                           ▼                                              │
│                    ┌──────────────┐                                       │
│                    │   Storage    │  ◀── FileBased / Custom               │
│                    │   (持久化)    │                                       │
│                    └──────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Prompt Injection Flow                               │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌──────────┐    ┌────────────────────┐    ┌──────────────────────────┐   │
│   │ System   │───▶│  Memory Injection  │───▶│   LLM                    │   │
│   │ Prompt   │    │  (token budget)    │    │   (generate response)    │   │
│   └──────────┘    └────────┬───────────┘    └──────────────────────────┘   │
│                            │                                              │
│                            ▼                                              │
│                     ┌──────────────┐                                       │
│                     │   Storage    │                                       │
│                     │   (load)     │                                       │
│                     └──────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. MemoryStorage - 存储抽象层

```python
# 抽象接口
class MemoryStorage(abc.ABC):
    def load(agent_name, user_id) -> dict
    def save(memory_data, agent_name, user_id) -> bool
    def reload(agent_name, user_id) -> dict
```

**默认实现**: `FileMemoryStorage`
- 路径结构: `{base_dir}/users/{user_id}/agents/{agent_name}/memory.json`
- 缓存机制: 基于 mtime 的自动失效
- 原子写入: 使用临时文件 + rename 防止数据损坏
- 线程安全: `_cache_lock` 保护并发访问

#### 2. MemoryUpdateQueue - 异步更新队列

**关键特性**:

| 特性 | 说明 |
|------|------|
| **去重机制** | 同一 thread_id 的消息会被合并 |
| **防抖延迟** | 默认 30 秒，防止频繁更新 |
| **线程隔离** | `user_id` 在入队时捕获，穿越 Timer 线程边界 |
| **修正/强化信号** | 检测用户纠错或正面反馈，提升相关事实置信度 |

#### 3. MemoryUpdater - LLM 驱动的更新引擎

**更新流程**:
1. 加载当前记忆
2. 格式化对话历史
3. 构建 MEMORY_UPDATE_PROMPT
4. 调用 LLM 生成更新
5. 解析 JSON 响应
6. 应用更新到记忆
7. 过滤上传文件提及
8. 原子保存到存储

#### 4. MemoryMiddleware - Agent 中间件

```python
class MemoryMiddleware(AgentMiddleware):
    def after_agent(state, runtime) -> None:
        # 1. 过滤消息: 只保留 user + 最终 AI 响应
        # 2. 检测修正/强化信号
        # 3. 捕获 user_id (跨线程边界)
        # 4. 加入更新队列
```

### 记忆数据结构

```json
{
  "version": "1.0",
  "lastUpdated": "2026-05-10T12:00:00Z",
  "user": {
    "workContext": {
      "summary": "Core contributor, project names with metrics (16k+ stars), technical stack",
      "updatedAt": "2026-05-10T12:00:00Z"
    },
    "personalContext": {
      "summary": "Bilingual capabilities, specific interest areas, expertise domains",
      "updatedAt": "2026-05-10T12:00:00Z"
    },
    "topOfMind": {
      "summary": "Primary project work, parallel technical investigations, ongoing learning/tracking",
      "updatedAt": "2026-05-10T12:00:00Z"
    }
  },
  "history": {
    "recentMonths": { "summary": "...", "updatedAt": "..." },
    "earlierContext": { "summary": "...", "updatedAt": "..." },
    "longTermBackground": { "summary": "...", "updatedAt": "..." }
  },
  "facts": [
    {
      "id": "fact_abc12345",
      "content": "User prefers Python over JavaScript for backend",
      "category": "preference",
      "confidence": 0.85,
      "createdAt": "2026-05-01T10:00:00Z",
      "source": "thread_123"
    }
  ]
}
```

### 配置项 (`config.yaml`)

```yaml
memory:
  enabled: true                    # 启用记忆
  injection_enabled: true          # 注入到系统提示
  storage_path: ""                  # 空=按用户隔离存储
  storage_class: "deerflow.agents.memory.storage.FileMemoryStorage"
  debounce_seconds: 30             # 防抖延迟
  model_name: null                  # null=使用默认模型
  max_facts: 100                    # 事实上限
  fact_confidence_threshold: 0.7    # 最小置信度
  max_injection_tokens: 2000        # 注入token上限
```

---

## 四、实习项目借鉴指南

### 你的项目定位

```
目标：展示技术深度，GitHub 放代码
定位：预备实习项目 / 技术能力展示
```

### 你的技术架构

```
用户提问
    ↓
┌─────────────────────────────────────┐
│  Planner Agent（规划师）              │
│  • 分析问题类型                      │
│  • 拆解子任务                        │
│  • 决定调用哪些工具                   │
└─────────────────────────────────────┘
    ↓
┌──────────────┐    ┌──────────────────┐
│  Search Agent │ OR │  RAG Agent       │
│  （网络搜索）   │    │  （知识库检索）   │
└──────────────┘    └──────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Synthesizer Agent（汇总师）         │
│  • 整合结果                          │
│  • 生成最终回答                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Memory System（记忆系统）           │
│  • 短期：会话内上下文                  │
│  • 长期：向量存储关键信息              │
└─────────────────────────────────────┘
```

### 可借鉴模块对照

| 你项目模块 | DeerFlow 对应模块 | 借鉴价值 | 建议 |
|-----------|-----------------|---------|------|
| `agents/planner.py` | `deerflow/agents/lead_agent/` | ⭐⭐⭐⭐⭐ | 直接参考 Agent 工厂模式 |
| `agents/search_agent.py` | `deerflow/community/tavily/` | ⭐⭐⭐⭐ | 搜索工具直接复用 |
| `agents/rag_agent.py` | `deerflow/mcp/` | ⭐⭐⭐ | 工具加载模式可借鉴 |
| `agents/synthesizer.py` | `deerflow/agents/lead_agent/` | ⭐⭐⭐⭐ | LLM 调用模式可复用 |
| `memory/short_term.py` | `deerflow/agents/thread_state.py` | ⭐⭐⭐⭐ | 状态设计可借鉴 |
| `memory/long_term.py` | `deerflow/agents/memory/` | ⭐⭐⭐⭐⭐ | **可直接大幅复用** |
| `graph/research_graph.py` | `deerflow/agents/lead_agent/` + `langgraph.json` | ⭐⭐⭐⭐ | 图定义模式可借鉴 |
| `tools/` | `deerflow/tools/` + `deerflow/community/` | ⭐⭐⭐⭐ | 工具注册机制可借鉴 |
| `config.py` | `deerflow/config/` | ⭐⭐⭐⭐ | 配置分层设计可借鉴 |

### 推荐代码组织

```
research-assistant/
├── main.py
├── requirements.txt
├── config.yaml                 # 主配置 (参考 DeerFlow config.yaml)
│
├── config/                     # 配置模块 (借鉴 deerflow/config/)
│   ├── __init__.py
│   ├── models.py
│   ├── memory.py
│   └── tools.py
│
├── agents/                     # Agent 定义 (借鉴 deerflow/agents/)
│   ├── __init__.py
│   ├── planner.py              # 规划 Agent (核心)
│   ├── search_agent.py         # 搜索 Agent
│   ├── rag_agent.py            # RAG Agent
│   ├── synthesizer.py          # 汇总 Agent
│   └── base.py                 # Agent 基类
│
├── tools/                      # 工具集 (借鉴 deerflow/tools/)
│   ├── __init__.py
│   ├── search.py               # 搜索工具
│   ├── rag.py                  # RAG 工具
│   └── registry.py             # 工具注册表
│
├── memory/                     # 记忆系统 (直接复用 deerflow/agents/memory/)
│   ├── __init__.py
│   ├── queue.py                # 短期记忆队列
│   ├── storage.py              # 存储抽象
│   ├── updater.py              # LLM 更新
│   └── prompt.py               # 提示词模板
│
├── graph/                      # LangGraph (借鉴 deerflow/ + 自定义)
│   ├── __init__.py
│   ├── state.py                # 状态定义
│   └── research_graph.py       # 研究流程图
│
├── community/                  # 社区工具 (借鉴 deerflow/community/)
│   ├── tavily_search.py
│   └── duckduckgo_search.py
│
└── tests/                     # 测试
    ├── test_memory.py
    ├── test_agents.py
    └── test_graph.py
```

### 快速起步建议

**步骤 1**: 直接复用 DeerFlow 的 memory 模块
```bash
# 复制 memory 模块到你的项目
cp -r deer-flow/backend/packages/harness/deerflow/agents/memory/ your-project/memory/
```

**步骤 2**: 适配模型调用
```python
# 用 DeerFlow 的模型工厂，或直接用 langchain
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
```

**步骤 3**: 构建你的 LangGraph
```python
# 参考 deer-flow/backend/langgraph.json 的图结构定义
# 参考 deer-flow/backend/packages/harness/deerflow/agents/lead_agent/
```

### 差异化建议

你的实习项目要展示技术深度，可以：

| 方向 | DeerFlow 做法 | 你的差异化 |
|------|-------------|-----------|
| **Planner** | 通用规划 | 加入思维链可视化 |
| **Memory** | 文件存储 | 换用向量数据库 (Chroma) + SQLite |
| **RAG** | 工具调用 | 加入重排序、混合检索 |
| **评估** | 无 | 加入答案质量评估指标 |
| **可视化** | 无 | 添加 LangGraph 可视化调试界面 |

---

## 五、关键设计决策

| 决策 | 原因 | 适用场景 |
|------|------|---------|
| **去重队列 + 防抖** | 减少 LLM 调用频率，合并短时间内的多次更新 | 高频交互场景 |
| **user_id 入队捕获** | Timer 线程无法访问 ContextVar，必须显式传递 | 异步记忆更新 |
| **事实内容归一化** | 大小写折叠后比较，防止重复事实累积 | 长期记忆累积 |
| **上传文件过滤** | 会话级信息不应进入长期记忆，避免误导 | 文档处理场景 |
| **原子文件写入** | 防止进程崩溃导致记忆数据损坏 | 生产环境可靠性 |
| **Token 预算注入** | 控制上下文长度，避免超出模型限制 | 长对话场景 |
| **中间件链式设计** | 职责单一，可组合，可测试 | 复杂 Agent 场景 |
| **Harness/App 分层** | 框架可发布，应用层解耦 | 库/框架设计 |

---

## 六、核心文件索引

| 功能 | 文件路径 |
|------|---------|
| **Agent 系统** | `backend/packages/harness/deerflow/agents/lead_agent/` |
| **Memory 系统** | `backend/packages/harness/deerflow/agents/memory/` |
| **中间件** | `backend/packages/harness/deerflow/agents/middlewares/` |
| **子 Agent** | `backend/packages/harness/deerflow/subagents/` |
| **沙箱系统** | `backend/packages/harness/deerflow/sandbox/` |
| **工具系统** | `backend/packages/harness/deerflow/tools/` + `community/` |
| **配置系统** | `backend/packages/harness/deerflow/config/` |
| **MCP 集成** | `backend/packages/harness/deerflow/mcp/` |
| **网关 API** | `backend/app/gateway/` |
| **IM 渠道** | `backend/app/channels/` |
| **LangGraph 图** | `backend/langgraph.json` |
| **架构文档** | `backend/CLAUDE.md` |

---

## 七、参考资料

- **GitHub**: https://github.com/bytedance/deer-flow
- **官方文档**: https://deerflow.tech
- **LangChain**: https://github.com/langchain-ai/langchain
- **LangGraph**: https://github.com/langchain-ai/langgraph
- **Python 版本**: 3.12+
- **Node.js 版本**: 22+