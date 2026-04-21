import asyncio
import json
import os
import time
from typing import List

from agent.main_agent import MainAgent
from engine.advanced_evaluator import AdvancedEvaluator
from engine.llm_judge import LLMJudge
from engine.runner import BenchmarkRunner


class ExpertEvaluator:
    def __init__(self):
        self._evaluator = AdvancedEvaluator()

    async def score(self, case, resp):
        return await self._evaluator.score(case, resp)


class MultiModelJudge:
    def __init__(self):
        self._judge = LLMJudge()

    async def evaluate_multi_judge(self, q, a, gt):
        return await self._judge.evaluate_multi_judge(q, a, gt)

    async def check_position_bias(self, response_a, response_b, question="", ground_truth=""):
        return await self._judge.check_position_bias(
            response_a=response_a,
            response_b=response_b,
            question=question,
            ground_truth=ground_truth,
        )


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def _resolve_agent_version(agent_version: str) -> str:
    normalized = (agent_version or "").strip().lower()
    return "v1" if "v1" in normalized else "v2"


async def run_benchmark_with_results(agent_version: str):
    print(f"Khoi dong benchmark cho {agent_version}...")

    if not os.path.exists("data/golden_set.jsonl"):
        print("Thieu data/golden_set.jsonl. Hay chay 'python data/synthetic_gen.py' truoc.")
        return None, None

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print("File data/golden_set.jsonl rong. Hay tao it nhat 1 test case.")
        return None, None

    benchmark_started_at = time.perf_counter()
    runtime_version = _resolve_agent_version(agent_version)
    runner = BenchmarkRunner(
        MainAgent(version=runtime_version),
        ExpertEvaluator(),
        MultiModelJudge(),
    )
    results = await runner.run_all(dataset)
    benchmark_duration_sec = time.perf_counter() - benchmark_started_at

    retrieval_metrics = [result.get("ragas", {}).get("retrieval", {}) for result in results]
    usage_totals = [result.get("usage", {}).get("total", {}) for result in results]
    latencies = [float(result.get("latency", 0.0)) for result in results]
    unpriced_models = sorted(
        {
            model
            for usage in usage_totals
            for model in usage.get("unpriced_models", [])
        }
    )

    total = len(results)
    summary = {
        "metadata": {
            "version": agent_version,
            "agent_runtime_version": runtime_version,
            "total": total,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "benchmark_duration_sec": round(benchmark_duration_sec, 6),
        },
        "metrics": {
            "avg_score": _mean([result.get("judge", {}).get("final_score", 0.0) for result in results]),
            "hit_rate": _mean([metric.get("hit_rate", 0.0) for metric in retrieval_metrics]),
            "mrr": _mean([metric.get("mrr", 0.0) for metric in retrieval_metrics]),
            "context_precision": _mean([metric.get("context_precision", 0.0) for metric in retrieval_metrics]),
            "context_recall": _mean([metric.get("context_recall", 0.0) for metric in retrieval_metrics]),
            "faithfulness": _mean([result.get("ragas", {}).get("faithfulness", 0.0) for result in results]),
            "relevancy": _mean([result.get("ragas", {}).get("relevancy", 0.0) for result in results]),
            "semantic_similarity": _mean([result.get("ragas", {}).get("semantic_similarity", 0.0) for result in results]),
            "agreement_rate": _mean([result.get("judge", {}).get("agreement_rate", 0.0) for result in results]),
            "position_bias_rate": _mean(
                [1.0 if result.get("position_bias", {}).get("bias_detected") else 0.0 for result in results]
            ),
            "avg_latency_sec": _mean(latencies),
            "p95_latency_sec": _p95(latencies),
            "pass_rate": _mean([1.0 if result.get("status") == "pass" else 0.0 for result in results]),
            "total_cost_usd": round(sum(usage.get("cost_usd", 0.0) for usage in usage_totals), 8),
            "cost_per_eval_usd": round(_mean([usage.get("cost_usd", 0.0) for usage in usage_totals]), 8),
            "total_tokens": sum(usage.get("total_tokens", 0) for usage in usage_totals),
            "avg_tokens_per_eval": _mean([usage.get("total_tokens", 0) for usage in usage_totals]),
        },
        "usage": {
            "input_tokens": sum(usage.get("input_tokens", 0) for usage in usage_totals),
            "output_tokens": sum(usage.get("output_tokens", 0) for usage in usage_totals),
            "total_tokens": sum(usage.get("total_tokens", 0) for usage in usage_totals),
            "total_cost_usd": round(sum(usage.get("cost_usd", 0.0) for usage in usage_totals), 8),
            "pricing_complete": len(unpriced_models) == 0,
            "unpriced_models": unpriced_models,
        },
    }
    return results, summary


async def run_benchmark(version):
    _, summary = await run_benchmark_with_results(version)
    return summary


async def main():
    v1_results, v1_summary = await run_benchmark_with_results("Agent_V1_Base")
    v2_results, v2_summary = await run_benchmark_with_results("Agent_V2_Optimized")

    if not v1_summary or not v2_summary:
        print("Khong the chay benchmark. Kiem tra lai data/golden_set.jsonl.")
        return

    print("\n--- KET QUA SO SANH (REGRESSION) ---")
    delta = v2_summary["metrics"]["avg_score"] - v1_summary["metrics"]["avg_score"]
    print(f"V1 Score: {v1_summary['metrics']['avg_score']:.4f}")
    print(f"V2 Score: {v2_summary['metrics']['avg_score']:.4f}")
    print(f"Delta: {'+' if delta >= 0 else ''}{delta:.4f}")

    regression = {
        "baseline": v1_summary["metadata"]["version"],
        "candidate": v2_summary["metadata"]["version"],
        "v1": {
            "score": v1_summary["metrics"]["avg_score"],
            "hit_rate": v1_summary["metrics"]["hit_rate"],
            "mrr": v1_summary["metrics"]["mrr"],
            "context_precision": v1_summary["metrics"]["context_precision"],
            "context_recall": v1_summary["metrics"]["context_recall"],
            "judge_agreement": v1_summary["metrics"]["agreement_rate"],
        },
        "v2": {
            "score": v2_summary["metrics"]["avg_score"],
            "hit_rate": v2_summary["metrics"]["hit_rate"],
            "mrr": v2_summary["metrics"]["mrr"],
            "context_precision": v2_summary["metrics"]["context_precision"],
            "context_recall": v2_summary["metrics"]["context_recall"],
            "judge_agreement": v2_summary["metrics"]["agreement_rate"],
        },
        "delta_avg_score": round(delta, 8),
        "delta_hit_rate": round(v2_summary["metrics"]["hit_rate"] - v1_summary["metrics"]["hit_rate"], 8),
        "delta_mrr": round(v2_summary["metrics"]["mrr"] - v1_summary["metrics"]["mrr"], 8),
        "delta_context_precision": round(
            v2_summary["metrics"]["context_precision"] - v1_summary["metrics"]["context_precision"],
            8,
        ),
        "delta_context_recall": round(
            v2_summary["metrics"]["context_recall"] - v1_summary["metrics"]["context_recall"],
            8,
        ),
        "decision": "APPROVE" if delta > 0 else "BLOCK",
    }

    v2_summary["metadata"]["versions_compared"] = [
        v1_summary["metadata"]["version"],
        v2_summary["metadata"]["version"],
    ]
    v2_summary["regression"] = regression

    output_pairs = [
        ("summary.json", v2_summary),
        ("benchmark_results.json", {"v1": v1_results, "v2": v2_results}),
        (os.path.join("reports", "summary.json"), v2_summary),
        (os.path.join("reports", "benchmark_results.json"), {"v1": v1_results, "v2": v2_results}),
    ]

    os.makedirs("reports", exist_ok=True)
    for path, payload in output_pairs:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if delta > 0:
        print("QUYET DINH: CHAP NHAN BAN CAP NHAT (APPROVE)")
    else:
        print("QUYET DINH: TU CHOI (BLOCK RELEASE)")


if __name__ == "__main__":
    asyncio.run(main())
