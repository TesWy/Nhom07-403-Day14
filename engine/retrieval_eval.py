import asyncio
from typing import Dict, List

class RetrievalEvaluator:
    def __init__(self):
        # Stateless evaluator, safe to reuse across batches.
        pass

    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3) -> float:
        """
        Tính Hit Rate@K: có ít nhất 1 expected_id xuất hiện trong top_k retrieved_ids hay không.

        Quy ước cho câu out-of-context:
        - expected_ids rỗng và top_k rỗng => hit = 1.0
        - expected_ids rỗng nhưng có retrieve => hit = 0.0
        """
        if top_k <= 0:
            return 0.0

        expected = [x for x in expected_ids if x]
        top_retrieved = retrieved_ids[:top_k]

        if not expected:
            return 1.0 if not top_retrieved else 0.0

        hit = any(doc_id in top_retrieved for doc_id in expected)
        return 1.0 if hit else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Tính Reciprocal Rank cho 1 case.
        Tìm vị trí đầu tiên của một expected_id trong retrieved_ids.
        MRR = 1 / position (vị trí 1-indexed). Nếu không thấy thì là 0.

        Quy ước cho câu out-of-context:
        - expected_ids rỗng và retrieved_ids rỗng => RR = 1.0
        - expected_ids rỗng nhưng có retrieve => RR = 0.0
        """
        expected = [x for x in expected_ids if x]

        if not expected:
            return 1.0 if not retrieved_ids else 0.0

        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_context_precision(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Precision của tập context retrieve:
        relevant_retrieved / total_retrieved
        """
        expected = {x for x in expected_ids if x}
        retrieved = [x for x in dict.fromkeys(retrieved_ids) if x]

        if not expected:
            return 1.0 if not retrieved else 0.0

        if not retrieved:
            return 0.0

        relevant_retrieved = sum(1 for doc_id in retrieved if doc_id in expected)
        return relevant_retrieved / len(retrieved)

    def calculate_context_recall(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Recall của tập context retrieve:
        relevant_retrieved / all_relevant_in_corpus
        """
        expected = {x for x in expected_ids if x}
        retrieved = {x for x in retrieved_ids if x}

        if not expected:
            return 1.0 if not retrieved else 0.0

        relevant_retrieved = sum(1 for doc_id in expected if doc_id in retrieved)
        return relevant_retrieved / len(expected)

    @staticmethod
    def _get_expected_ids(item: Dict) -> List[str]:
        return (
            item.get("expected_chunk_ids")
            or item.get("expected_retrieval_ids")
            or []
        )

    @staticmethod
    def _get_retrieved_ids(item: Dict) -> List[str]:
        if item.get("retrieved_ids"):
            return item["retrieved_ids"]

        response = item.get("response") or item.get("agent_response") or {}
        if isinstance(response, dict):
            metadata = response.get("metadata") or {}
            if metadata.get("retrieved_chunk_ids"):
                return metadata["retrieved_chunk_ids"]

        metadata = item.get("metadata") or {}
        if metadata.get("retrieved_chunk_ids"):
            return metadata["retrieved_chunk_ids"]

        return []

    async def evaluate_batch(self, dataset: List[Dict]) -> Dict:
        """
        Chạy eval cho toàn bộ bộ dữ liệu.
        Dataset chấp nhận các key expected ids:
        - expected_chunk_ids
        - expected_retrieval_ids
        Và các key retrieved ids:
        - retrieved_ids
        - response/agent_response.metadata.retrieved_chunk_ids
        """
        if not dataset:
            return {
                "avg_hit_rate": 0.0,
                "avg_mrr": 0.0,
                "avg_context_precision": 0.0,
                "avg_context_recall": 0.0,
                "count": 0,
                "per_case": [],
            }

        hit_scores: List[float] = []
        mrr_scores: List[float] = []
        context_precision_scores: List[float] = []
        context_recall_scores: List[float] = []
        per_case: List[Dict] = []

        for idx, item in enumerate(dataset):
            expected_ids = self._get_expected_ids(item)
            retrieved_ids = self._get_retrieved_ids(item)

            hit = self.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3)
            mrr = self.calculate_mrr(expected_ids, retrieved_ids)
            context_precision = self.calculate_context_precision(expected_ids, retrieved_ids)
            context_recall = self.calculate_context_recall(expected_ids, retrieved_ids)

            hit_scores.append(hit)
            mrr_scores.append(mrr)
            context_precision_scores.append(context_precision)
            context_recall_scores.append(context_recall)
            per_case.append(
                {
                    "index": idx,
                    "expected_ids": expected_ids,
                    "retrieved_ids": retrieved_ids,
                    "hit_rate": hit,
                    "mrr": mrr,
                    "context_precision": context_precision,
                    "context_recall": context_recall,
                }
            )

        await asyncio.sleep(0)
        return {
            "avg_hit_rate": sum(hit_scores) / len(hit_scores),
            "avg_mrr": sum(mrr_scores) / len(mrr_scores),
            "avg_context_precision": sum(context_precision_scores) / len(context_precision_scores),
            "avg_context_recall": sum(context_recall_scores) / len(context_recall_scores),
            "count": len(dataset),
            "per_case": per_case,
        }
