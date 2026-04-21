import json
import os
from typing import Any, Dict


def resolve_output_path(*candidates: str) -> str:
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def _load_json(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        print(f"[ERROR] Missing file: {path}")
        return None
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON in {path}: {exc}")
        return None

    if not isinstance(payload, dict):
        print(f"[ERROR] File {path} must be a JSON object.")
        return None
    return payload


def _require_keys(payload: Dict[str, Any], keys: list[str], label: str) -> bool:
    missing = [key for key in keys if key not in payload]
    if missing:
        print(f"[ERROR] {label} missing keys: {missing}")
        return False
    return True


def _validate_summary(summary_path: str) -> bool:
    data = _load_json(summary_path)
    if data is None:
        return False

    if not _require_keys(data, ["metadata", "metrics", "regression"], "summary.json"):
        return False

    metadata = data["metadata"]
    metrics = data["metrics"]
    regression = data["regression"]

    if not isinstance(metadata, dict) or not isinstance(metrics, dict) or not isinstance(regression, dict):
        print("[ERROR] summary.json has invalid structure: metadata/metrics/regression must be objects.")
        return False

    required_metrics = [
        "avg_score",
        "hit_rate",
        "mrr",
        "context_precision",
        "context_recall",
        "faithfulness",
        "relevancy",
        "semantic_similarity",
        "agreement_rate",
        "position_bias_rate",
        "avg_latency_sec",
        "p95_latency_sec",
        "pass_rate",
        "total_cost_usd",
        "cost_per_eval_usd",
        "total_tokens",
        "avg_tokens_per_eval",
    ]
    if not _require_keys(metrics, required_metrics, "summary.metrics"):
        return False

    if not _require_keys(metadata, ["version", "total", "timestamp"], "summary.metadata"):
        return False

    if not _require_keys(regression, ["v1", "v2", "decision"], "summary.regression"):
        return False

    print("\n--- Quick Stats ---")
    print(f"Total cases: {metadata.get('total', 'N/A')}")
    print(f"Average score: {metrics.get('avg_score', 0):.2f}")
    print(f"[OK] Hit Rate: {metrics['hit_rate']*100:.1f}%")
    print(f"[OK] MRR: {metrics['mrr']:.3f}")
    print(
        f"[OK] Context Quality: precision={metrics['context_precision']:.3f}, "
        f"recall={metrics['context_recall']:.3f}"
    )
    print(f"[OK] Semantic Similarity: {metrics['semantic_similarity']:.3f}")
    print(f"[OK] Faithfulness: {metrics['faithfulness']:.3f}")
    print(f"[OK] Relevancy: {metrics['relevancy']:.3f}")
    print(f"[OK] Agreement Rate: {metrics['agreement_rate']*100:.1f}%")
    print(f"[OK] Position Bias Rate: {metrics['position_bias_rate']*100:.1f}%")
    print(f"[OK] Avg Latency: {metrics['avg_latency_sec']:.3f}s")
    print(f"[OK] P95 Latency: {metrics['p95_latency_sec']:.3f}s")
    print(f"[OK] Cost: ${metrics['total_cost_usd']:.6f} total, ${metrics['cost_per_eval_usd']:.6f}/eval")
    print(f"[OK] Token Usage: {metrics['total_tokens']} total")
    print(f"[OK] Regression Decision: {regression['decision']}")
    return True


def _validate_case(case: Dict[str, Any], label: str) -> bool:
    if not _require_keys(case, ["test_case", "agent_response", "latency", "ragas", "judge", "status"], label):
        return False

    ragas = case["ragas"]
    judge = case["judge"]
    if not isinstance(ragas, dict) or not isinstance(judge, dict):
        print(f"[ERROR] {label} has invalid ragas/judge types.")
        return False

    if not _require_keys(ragas, ["retrieval", "faithfulness", "relevancy", "semantic_similarity"], f"{label}.ragas"):
        return False
    if not _require_keys(
        ragas["retrieval"],
        ["hit_rate", "mrr", "context_precision", "context_recall"],
        f"{label}.ragas.retrieval",
    ):
        return False
    if not _require_keys(
        judge,
        ["final_score", "agreement_rate", "individual_scores", "criterion_scores"],
        f"{label}.judge",
    ):
        return False
    return True


def _validate_benchmark_results(benchmark_path: str) -> bool:
    data = _load_json(benchmark_path)
    if data is None:
        return False

    if not _require_keys(data, ["v1", "v2"], "benchmark_results.json"):
        return False

    for version in ["v1", "v2"]:
        cases = data.get(version)
        if not isinstance(cases, list) or not cases:
            print(f"[ERROR] benchmark_results.json.{version} must be a non-empty list.")
            return False

        for idx, case in enumerate(cases[:3]):
            if not isinstance(case, dict):
                print(f"[ERROR] benchmark_results.json.{version}[{idx}] must be an object.")
                return False
            if not _validate_case(case, f"benchmark_results.{version}[{idx}]"):
                return False

    print(f"[OK] benchmark_results valid at {benchmark_path}")
    return True


def validate_lab():
    print("[CHECK] Validating submission format...")

    summary_path = resolve_output_path("summary.json", "reports/summary.json")
    benchmark_path = resolve_output_path("benchmark_results.json", "reports/benchmark_results.json")
    analysis_path = "analysis/failure_analysis.md"

    if not os.path.exists(analysis_path):
        print(f"[ERROR] Missing file: {analysis_path}")
        return
    print(f"[OK] Found: {summary_path}")
    print(f"[OK] Found: {benchmark_path}")
    print(f"[OK] Found: {analysis_path}")

    summary_ok = _validate_summary(summary_path)
    benchmark_ok = _validate_benchmark_results(benchmark_path)

    if summary_ok and benchmark_ok:
        print("\n[PASS] Submission outputs are ready for grading.")
    else:
        print("\n[FAIL] Submission outputs did not pass validation.")


if __name__ == "__main__":
    validate_lab()
