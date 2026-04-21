import os
from typing import Dict, List

import numpy as np


class AdvancedEvaluator:
    """
    Real semantic metrics backed by sentence-transformers when available.
    Falls back to TF-IDF cosine similarity if the embedding model cannot load.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv(
            "SEMANTIC_SIMILARITY_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        self._model = None
        self._embedding_cache: Dict[str, np.ndarray] = {}

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            self._model = False
            return self._model

        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception:
            self._model = False
        return self._model

    def _embed(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.zeros(384, dtype=float)

        if text in self._embedding_cache:
            return self._embedding_cache[text]

        model = self._get_model()
        if model is False:
            embedding = np.zeros(384, dtype=float)
        else:
            embedding = model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

        self._embedding_cache[text] = np.asarray(embedding, dtype=float)
        return self._embedding_cache[text]

    @staticmethod
    def _tfidf_similarity(text_a: str, text_b: str) -> float:
        if not text_a.strip() or not text_b.strip():
            return 0.0

        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform([text_a, text_b]).toarray()
        return AdvancedEvaluator._cosine_similarity(matrix[0], matrix[1])

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        denominator = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denominator == 0.0:
            return 0.0

        cosine = float(np.dot(vec_a, vec_b) / denominator)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    def _semantic_similarity(self, text_a: str, text_b: str) -> float:
        if not text_a.strip() or not text_b.strip():
            return 0.0

        if self._get_model() is False:
            return self._tfidf_similarity(text_a, text_b)

        return self._cosine_similarity(self._embed(text_a), self._embed(text_b))

    def _grounding_score(self, answer: str, contexts: List[str]) -> float:
        valid_contexts = [ctx for ctx in contexts if isinstance(ctx, str) and ctx.strip()]
        if not valid_contexts:
            return 0.0

        joined_context = "\n\n".join(valid_contexts)
        return self._semantic_similarity(answer, joined_context)

    async def score(self, case: Dict, response: Dict) -> Dict:
        answer = (response.get("answer", "") or "").strip()
        question = (case.get("question", "") or "").strip()
        expected_answer = (case.get("expected_answer", "") or "").strip()
        contexts = response.get("contexts") or []

        semantic_similarity = self._semantic_similarity(answer, expected_answer)
        answer_question_similarity = self._semantic_similarity(answer, question)
        faithfulness = self._grounding_score(answer, contexts)
        relevancy = (semantic_similarity + answer_question_similarity) / 2.0

        return {
            "semantic_similarity": round(semantic_similarity, 6),
            "faithfulness": round(faithfulness, 6),
            "relevancy": round(relevancy, 6),
        }
