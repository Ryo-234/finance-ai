# Research Agent - 智能研究助手

基于 DeerFlow 架构的 AI 研究代理系统，支持多 Agent 协作、持久化记忆和知识库检索。

## 技术栈

- **后端**: Python 3.12+ / LangGraph / LangChain / FastAPI
- **模型**: OpenAI GPT-4 / Claude / vLLM
- **记忆**: 文件存储 + 向量数据库（可选）
- **搜索**: Tavily / DuckDuckGo

## 项目结构

```
research_agent/
├── main.py              # 入口文件
├── config.yaml           # 主配置文件
├── requirements.txt      # 依赖
│
├── config/               # 配置模块
│   ├── __init__.py
│   ├── models.py         # 模型配置
│   ├── memory.py         # 记忆配置
│   └── tools.py          # 工具配置
│
├── agents/               # Agent 定义
│   ├── __init__.py
│   ├── base.py           # Agent 基类
│   ├── planner.py        # 规划 Agent（核心）
│   ├── search_agent.py   # 搜索 Agent
│   ├── rag_agent.py      # RAG Agent
│   └── synthesizer.py    # 汇总 Agent
│
├── tools/                # 工具集
│   ├── __init__.py
│   ├── search.py         # 搜索工具
│   ├── rag.py            # RAG 工具
│   └── registry.py       # 工具注册表
│
├── memory/               # 记忆系统（参考 DeerFlow）
│   ├── __init__.py
│   ├── storage.py        # 存储抽象
│   ├── queue.py          # 更新队列
│   ├── updater.py        # LLM 更新
│   ├── prompt.py         # 提示词模板
│   └── message_processing.py  # 消息处理
│
├── graph/                # LangGraph
│   ├── __init__.py
│   ├── state.py          # 状态定义
│   └── research_graph.py # 研究流程图
│
├── community/            # 社区工具
│   ├── __init__.py
│   ├── tavily_search.py  # Tavily 搜索
│   └── duckduckgo_search.py  # DuckDuckGo 搜索
│
└── tests/                # 测试
    ├── __init__.py
    ├── test_memory.py
    ├── test_agents.py
    └── test_graph.py
```

## 核心架构

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
│  • 长期：文件存储关键信息              │
└─────────────────────────────────────┘
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
export OPENAI_API_KEY="your-api-key"

# 运行
python main.py
```

## License

MIT