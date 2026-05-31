"""RAG Agent - 基于 ChromaDB 向量检索的知识库增强。"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.text_splitter import CharacterTextSplitter

from agents.base import BaseAgent, AgentConfig, state_to_dict, state_get

logger = logging.getLogger(__name__)

# 嵌入维度：DashScope text-embedding-v1 输出 1536 维
_EMBEDDING_DIM = 1536
_COLLECTION_NAME = "research_docs"


class RagAgent(BaseAgent):
    """RAG Agent —— 从本地文档向量库检索相关信息。

    使用 ChromaDB 存储文档嵌入，支持：
    1. 从 data/documents/ 目录加载文本文档建立索引
    2. 根据用户查询检索最相关的文档片段
    3. 返回带来源标注的上下文
    """

    def __init__(self, model=None):
        super().__init__(
            config=AgentConfig(
                name="rag",
                description="RAG Agent - 从本地知识库检索文档",
                model=model,
                system_prompt="""你是一个知识库检索助手。
                根据用户问题从本地文档库中检索相关信息，提供准确的上下文。""",
            )
        )
        self._collection = None
        self._embedding_fn = None

    def _get_collection(self):
        """获取或初始化 ChromaDB 集合（懒加载）。"""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
        except ImportError:
            logger.warning("chromadb 未安装，RAG 检索将不可用")
            return None

        persist_dir = os.path.join("data", "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)

        client = chromadb.PersistentClient(path=persist_dir)
        self._collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"description": "Research Agent 文档知识库"},
        )
        logger.info("ChromaDB 集合已加载，当前文档数: %d", self._collection.count())
        return self._collection

    def _get_embedding_fn(self):
        """获取嵌入函数（使用 DashScope text-embedding-v1）。"""
        if self._embedding_fn is not None:
            return self._embedding_fn

        # 尝试使用 DashScope 嵌入
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
        if dashscope_key:
            try:
                from langchain_community.embeddings import DashScopeEmbeddings
                self._embedding_fn = DashScopeEmbeddings(
                    model="text-embedding-v1",
                    dashscope_api_key=dashscope_key,
                )
                logger.info("使用 DashScope text-embedding-v1 嵌入模型")
                return self._embedding_fn
            except ImportError:
                logger.warning("langchain_community 未安装，无法使用 DashScope 嵌入")

            # 回退：直接调用 DashScope HTTP API
            try:
                import requests

                class DashScopeHTTPEmbedding:
                    def embed_documents(self, texts: List[str]) -> List[List[float]]:
                        results = []
                        for text in texts:
                            resp = requests.post(
                                "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
                                headers={"Authorization": f"Bearer {dashscope_key}"},
                                json={
                                    "model": "text-embedding-v1",
                                    "input": {"texts": [text]},
                                },
                                timeout=30,
                            )
                            data = resp.json()
                            if data.get("output") and data["output"].get("embeddings"):
                                results.append(data["output"]["embeddings"][0]["embedding"])
                            else:
                                # 嵌入失败时返回零向量
                                results.append([0.0] * _EMBEDDING_DIM)
                        return results

                    def embed_query(self, text: str) -> List[float]:
                        embeddings = self.embed_documents([text])
                        return embeddings[0] if embeddings else [0.0] * _EMBEDDING_DIM

                self._embedding_fn = DashScopeHTTPEmbedding()
                logger.info("使用 DashScope HTTP API 嵌入（回退方案）")
                return self._embedding_fn
            except ImportError:
                pass

        # 最终回退：简单 TF-IDF 模拟（仅用于开发调试）
        logger.warning("未配置嵌入模型，使用简单关键词匹配回退方案")
        self._embedding_fn = _SimpleKeywordMatcher()
        return self._embedding_fn

    def index_documents(self, doc_dir: str = "data/documents") -> int:
        """从目录加载文本文档并建立索引。

        返回成功索引的文档片段数量。
        """
        doc_path = Path(doc_dir)
        if not doc_path.exists():
            logger.warning("文档目录不存在: %s", doc_dir)
            doc_path.mkdir(parents=True, exist_ok=True)
            return 0

        # 收集所有文本文件
        texts = []
        metadatas = []
        ids = []

        text_extensions = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".log"}
        for file_path in doc_path.rglob("*"):
            if file_path.suffix not in text_extensions:
                continue
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                if not content.strip():
                    continue
                # 分割长文档
                splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
                chunks = splitter.split_text(content)
                for i, chunk in enumerate(chunks):
                    texts.append(chunk)
                    metadatas.append({
                        "source": str(file_path.relative_to(doc_path)),
                        "chunk": i,
                    })
                    ids.append(f"{file_path.stem}_{i}")
            except Exception as e:
                logger.warning("读取文件失败 %s: %s", file_path, e)

        if not texts:
            logger.info("文档目录中没有可索引的文本文件")
            return 0

        collection = self._get_collection()
        embedding_fn = self._get_embedding_fn()
        if collection is None or embedding_fn is None:
            return 0

        # 批量嵌入并添加到集合
        try:
            embeddings = embedding_fn.embed_documents(texts)
            collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info("索引完成: %d 个文档片段", len(texts))
        except Exception as e:
            logger.error("索引失败: %s", e)
            return 0

        return len(texts)

    async def ainvoke(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从向量知识库检索相关文档。

        在执行前自动检查文档索引状态，如未索引则尝试加载。
        """
        state_dict = state_to_dict(state)

        if query is None:
            task = state_get(state_dict, "current_task")
            query = task.get("description", "") if task else state_get(state_dict, "user_input", "")

        rag_results = []

        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            # 尝试自动索引
            logger.info("向量库为空，尝试自动索引文档目录")
            self.index_documents()

            collection = self._get_collection()
            if collection is None or collection.count() == 0:
                return {
                    **state_dict,
                    "rag_query": query,
                    "rag_results": [],
                }

        embedding_fn = self._get_embedding_fn()
        if embedding_fn is None:
            return {
                **state_dict,
                "rag_query": query,
                "rag_results": [],
            }

        try:
            query_embedding = embedding_fn.embed_query(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=5,
            )

            if results and results.get("documents") and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    source = ""
                    if results.get("metadatas") and results["metadatas"][0][i]:
                        source = results["metadatas"][0][i].get("source", "")
                    rag_results.append({
                        "content": doc,
                        "source": source,
                        "relevance": round(
                            1.0 - (i * 0.15), 2
                        ) if results.get("distances") else None,
                    })

            logger.info("RAG 检索完成，查询: %s，命中 %d 条", query[:50], len(rag_results))

        except Exception as e:
            logger.error("RAG 检索失败: %s", e)

        return {
            **state_dict,
            "rag_query": query,
            "rag_results": rag_results,
        }


class _SimpleKeywordMatcher:
    """简单的关键词匹配回退方案（无需嵌入模型）。

    当没有配置嵌入 API 时使用，基于词频进行匹配。
    仅用于开发调试，生产环境请配置真实的嵌入模型。
    """

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 返回占位向量（不会被实际使用，因为 query 使用相同逻辑）
        return [[0.0] * _EMBEDDING_DIM for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        # 将查询词转为简单的词频向量
        words = set(text.lower().split())
        vec = [0.0] * _EMBEDDING_DIM
        for i, word in enumerate(words):
            if i >= _EMBEDDING_DIM:
                break
            vec[i] = float(hash(word) % 100) / 100.0
        return vec


def create_rag_agent(model=None) -> RagAgent:
    """创建 RAG Agent 工厂函数。"""
    return RagAgent(model=model)
