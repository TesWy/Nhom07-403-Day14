import asyncio
import time
from typing import List, Dict

from tqdm.auto import tqdm

from engine.retrieval_eval import RetrievalEvaluator

class BenchmarkRunner:
    def __init__(self, agent, evaluator, judge):
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge
        self.retrieval_eval = RetrievalEvaluator()

    @staticmethod
    def _extract_retrieved_ids(response: Dict) -> List[str]:
        if not isinstance(response, dict):
            return []

        if response.get("retrieved_ids"):
            return response.get("retrieved_ids", [])

        metadata = response.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("retrieved_chunk_ids"):
            return metadata.get("retrieved_chunk_ids", [])

        return []

    @staticmethod
    def _extract_expected_ids(test_case: Dict) -> List[str]:
        return (
            test_case.get("expected_chunk_ids")
            or test_case.get("expected_retrieval_ids")
            or []
        )

    async def _score_generation(self, test_case: Dict, response: Dict) -> Dict:
        if hasattr(self.evaluator, "score"):
            scored = self.evaluator.score(test_case, response)
            if asyncio.iscoroutine(scored):
                return await scored
            return scored or {}
        return {}

    async def run_single_test(self, test_case: Dict) -> Dict:
        start_time = time.perf_counter()

        question = test_case.get("question", "")
        expected_answer = test_case.get("expected_answer", "")

        try:
            # 1. Gọi Agent
            response = await self.agent.query(question)
        except Exception as exc:
            latency = time.perf_counter() - start_time
            return {
                "test_case": question,
                "agent_response": "",
                "agent_response_meta": {},
                "retrieved_ids": [],
                "latency": latency,
                "ragas": {},
                "judge": {
                    "final_score": 1,
                    "agreement_rate": 0.0,
                    "reasoning": f"Agent query failed: {exc}",
                },
                "status": "fail",
                "error": str(exc),
            }

        latency = time.perf_counter() - start_time
        answer = response.get("answer", "") if isinstance(response, dict) else ""
        retrieved_ids = self._extract_retrieved_ids(response)
        expected_ids = self._extract_expected_ids(test_case)

        # 2. Chạy metrics generation (RAGAS hoặc evaluator tùy biến)
        ragas_scores = await self._score_generation(test_case, response)

        # Bổ sung retrieval metrics nếu evaluator hiện tại chưa trả về.
        retrieval_scores = {
            "hit_rate": self.retrieval_eval.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3),
            "mrr": self.retrieval_eval.calculate_mrr(expected_ids, retrieved_ids),
        }
        if isinstance(ragas_scores, dict):
            ragas_scores.setdefault("retrieval", retrieval_scores)

        # 3. Chạy Multi-Judge
        judge_result = await self.judge.evaluate_multi_judge(question, answer, expected_answer)

        return {
            "test_case": question,
            "agent_response": answer,
            "agent_response_meta": response.get("metadata", {}) if isinstance(response, dict) else {},
            "retrieved_ids": retrieved_ids,
            "latency": latency,
            "ragas": ragas_scores,
            "judge": judge_result,
            "status": "fail" if judge_result.get("final_score", 0) < 3 else "pass"
        }

    async def run_all(self, dataset: List[Dict], batch_size: int = 5) -> List[Dict]:
        """
        Chạy song song bằng asyncio.gather với giới hạn batch_size để không bị Rate Limit.
        """
        if batch_size <= 0:
            batch_size = 1

        results = []
        for i in tqdm(
            range(0, len(dataset), batch_size),
            desc="Benchmark batches",
            unit="batch",
        ):
            batch = dataset[i:i + batch_size]
            tasks = [self.run_single_test(case) for case in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results
