import asyncio
import os
import json
from typing import List, Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv
import numpy as np

load_dotenv()

class MainAgent:
    """
    Base Agent class that defines the mandatory interface.
    """
    def __init__(self, version: str = "v2"):
        self.version = version
        api_key = os.getenv("OPENAI_API_KEY") or "no-key-found"
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"
        self.corpus = self._load_corpus()

    def _load_corpus(self) -> List[Dict[str, str]]:
        """
        Loads the corpus from data/corpus.jsonl (pre-chunked company policy documents
        with correct chunk IDs matching the golden_set.jsonl).
        Falls back to data/chunks/day08_rag_lab.jsonl, then to a minimal mock corpus.
        """
        # Primary: load from pre-chunked corpus with correct chunk IDs
        corpus_candidates = [
            "data/corpus.jsonl",
            "data/chunks/day08_rag_lab.jsonl",
        ]
        for corpus_path in corpus_candidates:
            if os.path.exists(corpus_path):
                corpus = []
                with open(corpus_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            corpus.append({
                                "chunk_id": obj.get("chunk_id", f"chunk_{len(corpus):03d}"),
                                "text": obj.get("text", obj.get("context", "")),
                                "source_doc": obj.get("source", obj.get("metadata", {}).get("source", "unknown")),
                            })
                        except json.JSONDecodeError:
                            continue
                if corpus:
                    return corpus

        # Last-resort fallback: minimal mock corpus
        return [
            {"chunk_id": "chunk_000", "text": "AI Evaluation là một quy trình kỹ thuật nhằm đo lường chất lượng hệ thống AI thông qua các chỉ số như Hit Rate, MRR, và LLM Judge.", "source_doc": "intro.txt"},
            {"chunk_id": "chunk_001", "text": "Hit Rate tính toán tỉ lệ các trường hợp mà tài liệu chính xác được tìm thấy trong Top-K kết quả trả về.", "source_doc": "metrics.txt"},
            {"chunk_id": "chunk_002", "text": "MRR (Mean Reciprocal Rank) đánh giá thứ hạng của kết quả đúng đầu tiên trong danh sách kết quả tìm kiếm.", "source_doc": "metrics.txt"},
        ]

    async def query(self, question: str) -> Dict:
        """
        Main query method. Delegates to V1 or V2 implementation.
        """
        if self.version == "v1":
            agent = AgentV1(self)
        else:
            agent = AgentV2(self)
        
        return await agent.query(question)

    async def _generate(self, question: str, contexts: List[str], system_prompt: str = None) -> str:
        """
        Common generation logic using OpenAI API.
        """
        if not system_prompt:
            system_prompt = "You are a helpful assistant. Use the provided context to answer."
        
        context_text = "\n\n".join(contexts)
        prompt = f"Context:\n{context_text}\n\nQuestion: {question}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error calling LLM: {str(e)}"

class AgentV1:
    """
    Agent V1: Retrieval cố tình kém.
    - Luôn trả về chunk đầu tiên trong corpus.
    - Prompt đơn giản.
    """
    def __init__(self, parent: MainAgent):
        self.parent = parent

    async def query(self, question: str) -> Dict:
        retrieved_chunks = self._broken_retrieve(question)
        answer = await self.parent._generate(question, retrieved_chunks)
        
        return {
            "answer": answer,
            "contexts": retrieved_chunks,
            "metadata": {
                "model": self.parent.model,
                "tokens_used": 150, # Dummy value
                "sources": ["intro.txt"],
                "retrieved_chunk_ids": ["chunk_000"] # Luôn cố định
            }
        }

    def _broken_retrieve(self, question: str) -> List[str]:
        # Luôn lấy chunk đầu tiên
        if self.parent.corpus:
            return [self.parent.corpus[0]["text"]]
        return []

class AgentV2:
    """
    Agent V2: Retrieval đúng chuẩn RAG.
    - Semantic search từ Vector DB (Simulated).
    - Lấy Top-K chunks.
    - Prompt có hướng dẫn rõ ràng.
    """
    def __init__(self, parent: MainAgent):
        self.parent = parent
        self._embeddings_cache = {}

    async def _get_embedding(self, text: str) -> np.ndarray:
        if text in self._embeddings_cache:
            return self._embeddings_cache[text]
        
        try:
            response = await self.parent.client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            embedding = np.array(response.data[0].embedding)
            self._embeddings_cache[text] = embedding
            return embedding
        except Exception:
            # Fallback to random if no API key
            return np.random.rand(1536)

    async def _semantic_retrieve(self, question: str, top_k: int = 3) -> List[Dict]:
        query_emb = await self._get_embedding(question)
        
        scored_chunks = []
        for chunk in self.parent.corpus:
            chunk_emb = await self._get_embedding(chunk["text"])
            score = np.dot(query_emb, chunk_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(chunk_emb))
            scored_chunks.append({**chunk, "score": score})
        
        # Sort by score and take top_k
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

    async def query(self, question: str) -> Dict:
        retrieved = await self._semantic_retrieve(question, top_k=3)
        retrieved_texts = [c["text"] for c in retrieved]
        
        system_prompt = (
            "Bạn là một trợ lý AI chuyên nghiệp. Chỉ trả lời câu hỏi dựa trên Context được cung cấp. "
            "Nếu Context không chứa thông tin cần thiết, hãy trả lời 'Tôi không có thông tin'."
        )
        
        answer = await self.parent._generate(question, retrieved_texts, system_prompt)
        
        return {
            "answer": answer,
            "contexts": retrieved_texts,
            "metadata": {
                "model": self.parent.model,
                "tokens_used": 250, # Dummy value
                "sources": list(set([c["source_doc"] for c in retrieved])),
                "retrieved_chunk_ids": [c["chunk_id"] for c in retrieved]
            }
        }

if __name__ == "__main__":
    async def test():
        print("Testing Agent V1...")
        v1 = MainAgent(version="v1")
        resp1 = await v1.query("AI Evaluation là gì?")
        print(f"V1 Answer: {resp1['answer']}")
        print(f"V1 Retrieved IDs: {resp1['metadata']['retrieved_chunk_ids']}\n")

        print("Testing Agent V2...")
        v2 = MainAgent(version="v2")
        resp2 = await v2.query("MRR là gì?")
        print(f"V2 Answer: {resp2['answer']}")
        print(f"V2 Retrieved IDs: {resp2['metadata']['retrieved_chunk_ids']}")

    asyncio.run(test())
