"""Tavily 搜索集成。"""

import os
from typing import List, Dict, Any, Optional


async def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """使用 Tavily API 执行搜索。

    参数：
        query: 搜索查询
        max_results: 最大结果数

    返回：
        搜索结果列表
    """
    try:
        from tavily import TavilyClient

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return [{"error": "未设置 TAVILY_API_KEY 环境变量"}]

        client = TavilyClient(api_key=api_key)
        results = client.search(query=query, max_results=max_results)

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            }
            for r in results.get("results", [])
        ]

    except ImportError:
        return [{"error": "请安装 tavily-python: pip install tavily"}]
    except Exception as e:
        return [{"error": f"Tavily 搜索失败: {str(e)}"}]


async def tavily_extract(url: str) -> Dict[str, Any]:
    """从 URL 提取内容。

    参数：
        url: 目标 URL

    返回：
        提取的内容
    """
    try:
        from tavily import TavilyClient

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return {"error": "未设置 TAVILY_API_KEY 环境变量"}

        client = TavilyClient(api_key=api_key)
        result = client.extract(urls=[url])

        return {
            "success": True,
            "content": result.get("results", [{}])[0].get("raw_content", ""),
        }

    except ImportError:
        return {"error": "请安装 tavily-python: pip install tavily"}
    except Exception as e:
        return {"error": f"内容提取失败: {str(e)}"}