"""DuckDuckGo 搜索集成。"""

from typing import List, Dict, Any


async def duckduckgo_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """使用 DuckDuckGo 执行搜索。

    参数：
        query: 搜索查询
        max_results: 最大结果数

    返回：
        搜索结果列表
    """
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("body", ""),
                    "score": 1.0,  # DuckDuckGo 没有相关性分数
                })

        return results

    except ImportError:
        return [{"error": "请安装 duckduckgo-search: pip install duckduckgo-search"}]
    except Exception as e:
        return [{"error": f"DuckDuckGo 搜索失败: {str(e)}"}]