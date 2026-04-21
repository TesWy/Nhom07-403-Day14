import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from dotenv import load_dotenv
from openai import AsyncOpenAI

from engine.llm_provider import LLMProviderAdapter
from engine.usage import build_usage_record, summarize_usage

load_dotenv()


class MainAgent:
    """
    Base agent class that defines the mandatory interface.
    """

    def __init__(self, version: str = "v2"):
        self.version = version
        self.repo_root = Path(__file__).resolve().parents[1]
        api_key = os.getenv("OPENAI_API_KEY") or "no-key-found"
        self.client = AsyncOpenAI(api_key=api_key)
        self.embedding_model = "text-embedding-3-small"
        self.generator = LLMProviderAdapter(provider_override=self._resolve_generation_provider())
        self.model = self.generator.get_active_model()
        self.corpus = self._load_corpus()
        self.embedding_dim = self._infer_embedding_dim()
        self._usage_records: List[Dict[str, Any]] = []
        self._local_embedding_model = None

    def _reset_usage(self) -> None:
        self._usage_records = []

    def _record_usage(self, usage_record: Dict[str, Any] | None) -> None:
        if usage_record:
            self._usage_records.append(usage_record)

    @staticmethod
    def _resolve_generation_provider() -> str | None:
        explicit = os.getenv("AGENT_PROVIDER", "").strip().lower()
        if explicit:
            return explicit

        if os.getenv("OPENAI_API_KEY", "").strip():
            return "openai"

        has_aws = bool(
            (os.getenv("AWS_ACCESS_KEY_ID", "") or os.getenv("AWS_PROFILE", "")).strip()
        )
        if has_aws:
            return "bedrock"

        return None

    def _get_local_embedding_model(self):
        if self._local_embedding_model is not None:
            return self._local_embedding_model

        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            self._local_embedding_model = False
            return self._local_embedding_model

        model_name = os.getenv(
            "RETRIEVAL_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        try:
            self._local_embedding_model = SentenceTransformer(model_name)
        except Exception:
            self._local_embedding_model = False
        return self._local_embedding_model

    def _hash_embed(self, text: str, dim: int = 512) -> np.ndarray:
        vector = np.zeros(dim, dtype=float)
        for token in (text or "").lower().split():
            slot = abs(hash(token)) % dim
            vector[slot] += 1.0

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector

    def _load_corpus(self) -> List[Dict[str, Any]]:
        """
        Load the prepared Day14 corpus and preserve real chunk ids/source paths.
        """
        corpus_path = self.repo_root / "data" / "corpus.jsonl"
        corpus: List[Dict[str, Any]] = []

        if corpus_path.exists():
            with corpus_path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle):
                    line = line.strip()
                    if not line:
                        continue

                    row = json.loads(line)
                    metadata = row.get("metadata", {})
                    source_doc = (
                        row.get("source")
                        or metadata.get("source_document")
                        or metadata.get("source")
                        or "unknown"
                    )
                    chunk_id = row.get("chunk_id") or f"{Path(source_doc).stem}_{index}"
                    text = row.get("text") or row.get("context") or ""

                    if not text:
                        continue

                    corpus.append(
                        {
                            "chunk_id": chunk_id,
                            "text": text,
                            "context": row.get("context", text),
                            "source_doc": source_doc,
                            "metadata": metadata,
                            "chroma_ref": row.get("chroma_ref", {}),
                        }
                    )

        if corpus:
            return corpus

        fallback_dirs = [
            self.repo_root / "documents",
            self.repo_root / "data" / "docs",
            self.repo_root / "data" / "legacy" / "day08" / "docs",
        ]

        for docs_dir in fallback_dirs:
            if not docs_dir.exists():
                continue

            txt_files = sorted(docs_dir.glob("*.txt"))
            if not txt_files:
                continue

            for file_path in txt_files:
                text = file_path.read_text(encoding="utf-8")
                corpus.append(
                    {
                        "chunk_id": f"{file_path.stem}_doc",
                        "text": text,
                        "context": text,
                        "source_doc": file_path.name,
                        "metadata": {"source": file_path.name},
                        "chroma_ref": {},
                    }
                )

            if corpus:
                return corpus

        return []

    def _infer_embedding_dim(self) -> int:
        for chunk in self.corpus:
            metadata = chunk.get("metadata", {})
            chroma_ref = chunk.get("chroma_ref", {})

            if metadata.get("embedding_dimension"):
                return int(metadata["embedding_dimension"])
            if chroma_ref.get("embedding_dimension"):
                return int(chroma_ref["embedding_dimension"])

        return 1536

    def _build_metadata(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        answer: str,
    ) -> Dict[str, Any]:
        usage = summarize_usage(self._usage_records)
        return {
            "model": self.model,
            "answer_preview": answer[:120],
            "tokens_used": usage["total_tokens"],
            "cost_usd": usage["cost_usd"],
            "sources": sorted({chunk["source_doc"] for chunk in retrieved_chunks}),
            "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in retrieved_chunks],
            "usage": usage,
        }

    async def query(self, question: str) -> Dict[str, Any]:
        """
        Main query method. Delegates to V1 or V2 implementation.
        """
        self._reset_usage()

        if self.version == "v1":
            agent = AgentV1(self)
        else:
            agent = AgentV2(self)

        return await agent.query(question)

    async def _generate(
        self, question: str, contexts: List[str], system_prompt: str | None = None
    ) -> Dict[str, Any]:
        """
        Common generation logic using OpenAI API.
        """
        if not system_prompt:
            system_prompt = (
                "You are a helpful assistant. Use only the provided context to answer."
            )

        context_text = "\n\n".join(contexts)
        prompt = f"Context:\n{context_text}\n\nQuestion: {question}"

        try:
            result = await self.generator.generate_text_with_usage(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.0,
                max_tokens=600,
            )
            self._record_usage(result.get("usage"))
            return {"text": result.get("text", "")}
        except Exception as exc:
            return {"text": f"Error calling LLM: {exc}"}


class AgentV1:
    """
    Agent V1: intentionally weak retrieval.
    - Always returns access_control_sop_0 if available.
    - Keeps the real chunk_id/source_doc instead of fake placeholders.
    """

    def __init__(self, parent: MainAgent):
        self.parent = parent

    def _first_chunk(self) -> Dict[str, Any] | None:
        if not self.parent.corpus:
            return None

        for chunk in self.parent.corpus:
            if chunk.get("chunk_id") == "access_control_sop_0":
                return chunk

        return self.parent.corpus[0]

    async def query(self, question: str) -> Dict[str, Any]:
        first_chunk = self._first_chunk()
        retrieved_chunks = [first_chunk] if first_chunk else []
        generation = await self.parent._generate(
            question,
            [chunk["text"] for chunk in retrieved_chunks],
        )
        answer = generation["text"]

        return {
            "answer": answer,
            "contexts": [chunk["text"] for chunk in retrieved_chunks],
            "metadata": self.parent._build_metadata(retrieved_chunks, answer),
        }


class AgentV2:
    """
    Agent V2: normal retrieval flow.
    - Embedding-based retrieval when API is available.
    - Falls back to deterministic pseudo-embeddings if embeddings fail.
    """

    def __init__(self, parent: MainAgent):
        self.parent = parent
        self._embeddings_cache: Dict[str, np.ndarray] = {}

    async def _get_embedding(self, text: str) -> np.ndarray:
        if text in self._embeddings_cache:
            return self._embeddings_cache[text]

        if os.getenv("OPENAI_API_KEY", "").strip():
            try:
                response = await self.parent.client.embeddings.create(
                    input=text,
                    model=self.parent.embedding_model,
                )
                embedding = np.array(response.data[0].embedding)
                self.parent._record_usage(
                    build_usage_record(
                        provider="openai",
                        model=self.parent.embedding_model,
                        raw_usage=getattr(response, "usage", None),
                        operation="retrieval_embedding",
                    )
                )
            except Exception:
                embedding = None
        else:
            embedding = None

        if embedding is None:
            local_model = self.parent._get_local_embedding_model()
            if local_model is not False:
                embedding = np.asarray(
                    local_model.encode(
                        text,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                    ),
                    dtype=float,
                )
            else:
                embedding = self.parent._hash_embed(text)

        self._embeddings_cache[text] = embedding
        return embedding

    async def _semantic_retrieve(
        self, question: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        if not self.parent.corpus:
            return []

        query_emb = await self._get_embedding(question)
        scored_chunks: List[Dict[str, Any]] = []

        for chunk in self.parent.corpus:
            chunk_emb = await self._get_embedding(chunk["text"])
            denominator = np.linalg.norm(query_emb) * np.linalg.norm(chunk_emb)
            score = 0.0 if denominator == 0 else float(np.dot(query_emb, chunk_emb) / denominator)
            scored_chunks.append({**chunk, "score": score})

        scored_chunks.sort(key=lambda item: item["score"], reverse=True)
        return scored_chunks[:top_k]

    async def query(self, question: str) -> Dict[str, Any]:
        retrieved = await self._semantic_retrieve(question, top_k=3)
        retrieved_texts = [chunk["text"] for chunk in retrieved]

        system_prompt = (
            "You are a professional AI assistant. Answer only from the provided "
            "context. If the context does not contain the answer, reply with "
            "'Toi khong co thong tin'."
        )

        generation = await self.parent._generate(question, retrieved_texts, system_prompt)
        answer = generation["text"]

        return {
            "answer": answer,
            "contexts": retrieved_texts,
            "metadata": self.parent._build_metadata(retrieved, answer),
        }


if __name__ == "__main__":
    async def test() -> None:
        print("Testing Agent V1...")
        v1 = MainAgent(version="v1")
        resp1 = await v1.query("Level 3 access can ai phe duyet?")
        print(f"V1 Answer: {resp1['answer']}")
        print(f"V1 Retrieved IDs: {resp1['metadata']['retrieved_chunk_ids']}\n")

        print("Testing Agent V2...")
        v2 = MainAgent(version="v2")
        resp2 = await v2.query("Nhan vien moi trong 30 ngay dau duoc cap quyen Level may?")
        print(f"V2 Answer: {resp2['answer']}")
        print(f"V2 Retrieved IDs: {resp2['metadata']['retrieved_chunk_ids']}")

    asyncio.run(test())
