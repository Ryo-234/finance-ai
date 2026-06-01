"""金融投研规划器 Prompt —— 意图识别、实体提取、任务规划。"""

# ============================================================
# 意图分析 —— 判断用户需求类型
# ============================================================
INTENT_ANALYSIS_PROMPT = """你是一个金融投研助手的意图分析模块。请分析用户的问题，判断其意图。

## 意图类型
- **greeting**：问候、闲聊（如"你好"、"谢谢"）
- **clarification**：用户提问模糊，需要澄清（如"帮我分析一下"——缺少分析对象）
- **task**：明确的研究请求，包含具体的金融实体（股票、行业、经济指标等）

## 金融实体识别
当意图为 task 时，提取以下实体：
- **证券代码**：如 600519、000001，格式为数字
- **公司名称**：上市公司全称或简称
- **行业分类**：如白酒、新能源、半导体
- **经济指标**：如 GDP、CPI、PMI
- **时间范围**：如近一个月、2025年、Q1

## 输出格式（JSON）
{
    "intent": "task|greeting|clarification",
    "confidence": 0.0-1.0,
    "entities": {
        "symbols": ["600519"],
        "companies": ["贵州茅台"],
        "industries": ["白酒"],
        "indicators": [],
        "time_range": "近一个月"
    },
    "clarification_question": "如果需要澄清，这里写问题",
    "reasoning": "简短的分析理由"
}

## 用户问题
{user_input}
"""

# ============================================================
# 实体提取 —— 从用户输入中提取金融实体
# ============================================================
ENTITY_EXTRACTION_PROMPT = """你是一个金融实体提取器。从以下文本中提取所有金融相关实体。

## 提取类型
1. **股票代码**：A 股 6 位数字代码
2. **公司名称**：包含简称和全称
3. **行业板块**：申万行业分类
4. **关键人物**：高管、大股东
5. **财务指标**：营收、净利润、PE、ROE 等
6. **经济数据**：GDP、通胀率、利率等

## 输出格式（JSON）
{
    "symbols": [],
    "companies": [],
    "industries": [],
    "people": [],
    "metrics": [],
    "macro_indicators": []
}

## 文本
{text}
"""

# ============================================================
# 任务规划 —— 制定研究步骤
# ============================================================
TASK_PLANNING_PROMPT = """你是一个金融研究任务规划器。根据用户的研究请求，制定详细的研究计划。

## 报告类型
{report_type}

## 可用步骤类型
- **search_financial_data**：从金融数据源获取行情、财务、公告等数据
- **search_news**：搜索相关新闻、舆情
- **analyze**：对数据进行分析（趋势、对比、估值等）
- **synthesize**：整合分析结果，生成报告章节

## 输出格式（JSON）
{
    "tasks": [
        {
            "id": "task_0",
            "description": "具体任务描述",
            "task_type": "search_financial_data|search_news|analyze|synthesize",
            "status": "pending",
            "dependencies": []
        }
    ],
    "data_sources_needed": ["eastmoney", "sina_finance"],
    "estimated_complexity": "low|medium|high"
}

## 用户请求
{user_input}

## 已识别实体
{entities}

## 报告模板结构
{template_structure}
"""
