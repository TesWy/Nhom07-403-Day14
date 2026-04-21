import asyncio
import time
from typing import Dict, List

from tqdm.auto import tqdm

from engine.retrieval_eval import RetrievalEvaluator
from engine.usage import merge_usage_payloads


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
            response = await self.agent.query(question)
        except Exception as exc:
            latency = time.perf_counter() - start_time
            return {
                "test_case": question,
                "agent_response": "",
                "agent_response_meta": {},
                "retrieved_ids": [],
                "latency": latency,
                "ragas": {
                    "retrieval": {
                        "hit_rate": 0.0,
                        "mrr": 0.0,
                        "context_precision": 0.0,
                        "context_recall": 0.0,
                    }
                },
                "judge": {
                    "final_score": 1,
                    "agreement_rate": 0.0,
                    "reasoning": f"Agent query failed: {exc}",
                    "usage": merge_usage_payloads(),
                },
                "position_bias": {
                    "preferred_when_a_first": "tie",
                    "preferred_when_b_first": "tie",
                    "bias_detected": False,
                    "usage": merge_usage_payloads(),
                },
                "usage": {"total": merge_usage_payloads()},
                "status": "fail",
                "error": str(exc),
            }

        latency = time.perf_counter() - start_time
        answer = response.get("answer", "") if isinstance(response, dict) else ""
        retrieved_ids = self._extract_retrieved_ids(response)
        expected_ids = self._extract_expected_ids(test_case)

        generation_scores = await self._score_generation(test_case, response)
        if not isinstance(generation_scores, dict):
            generation_scores = {}

        retrieval_scores = {
            "hit_rate": self.retrieval_eval.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3),
            "mrr": self.retrieval_eval.calculate_mrr(expected_ids, retrieved_ids),
            "context_precision": self.retrieval_eval.calculate_context_precision(expected_ids, retrieved_ids),
            "context_recall": self.retrieval_eval.calculate_context_recall(expected_ids, retrieved_ids),
        }
        generation_scores["retrieval"] = retrieval_scores

        judge_result = await self.judge.evaluate_multi_judge(question, answer, expected_answer)
        position_bias = await self.judge.check_position_bias(
            response_a=answer,
            response_b=expected_answer,
            question=question,
            ground_truth=expected_answer,
        )

        agent_usage = (
            response.get("metadata", {}).get("usage", {})
            if isinstance(response, dict)
            else merge_usage_payloads()
        )
        total_usage = merge_usage_payloads(
            agent_usage,
            judge_result.get("usage"),
            position_bias.get("usage"),
        )

        return {
            "test_case": question,
            "agent_response": answer,
            "agent_response_meta": response.get("metadata", {}) if isinstance(response, dict) else {},
            "retrieved_ids": retrieved_ids,
            "latency": latency,
            "ragas": generation_scores,
            "judge": judge_result,
            "position_bias": position_bias,
            "usage": {
                "agent": agent_usage,
                "judge": judge_result.get("usage", merge_usage_payloads()),
                "position_bias": position_bias.get("usage", merge_usage_payloads()),
                "total": total_usage,
            },
            "status": "fail" if judge_result.get("final_score", 0) < 3 else "pass",
        }

    async def run_all(self, dataset: List[Dict], batch_size: int = 5) -> List[Dict]:
        """
        Run concurrent benchmark batches while limiting fanout to avoid rate limits.
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
