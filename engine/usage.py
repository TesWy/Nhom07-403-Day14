import json
import os
from typing import Any, Dict, Iterable, List


DEFAULT_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "openai:gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "openai:gpt-4o": {"input_per_1m": 5.00, "output_per_1m": 15.00},
    "openai:text-embedding-3-small": {"input_per_1m": 0.02, "output_per_1m": 0.00},
}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _maybe_get(obj: Any, *names: str) -> Any:
    if obj is None:
        return None

    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _load_pricing_overrides() -> Dict[str, Dict[str, float]]:
    raw = os.getenv("MODEL_PRICING_JSON", "").strip()
    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    overrides: Dict[str, Dict[str, float]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue

        input_price = value.get("input_per_1m")
        output_price = value.get("output_per_1m")
        if input_price is None and output_price is None:
            continue

        overrides[key] = {
            "input_per_1m": float(input_price or 0.0),
            "output_per_1m": float(output_price or 0.0),
        }
    return overrides


def _pricing_for(provider: str, model: str) -> Dict[str, float] | None:
    key = f"{provider}:{model}"
    overrides = _load_pricing_overrides()
    if key in overrides:
        return overrides[key]
    return DEFAULT_MODEL_PRICING.get(key)


def build_usage_record(
    provider: str,
    model: str,
    raw_usage: Any,
    operation: str,
) -> Dict[str, Any]:
    if provider == "openai":
        input_tokens = _safe_int(_maybe_get(raw_usage, "prompt_tokens", "input_tokens"))
        output_tokens = _safe_int(_maybe_get(raw_usage, "completion_tokens", "output_tokens"))
        total_tokens = _safe_int(_maybe_get(raw_usage, "total_tokens")) or (input_tokens + output_tokens)
    elif provider == "anthropic":
        input_tokens = _safe_int(_maybe_get(raw_usage, "input_tokens"))
        output_tokens = _safe_int(_maybe_get(raw_usage, "output_tokens"))
        total_tokens = _safe_int(_maybe_get(raw_usage, "total_tokens")) or (input_tokens + output_tokens)
    elif provider == "gemini":
        input_tokens = _safe_int(_maybe_get(raw_usage, "prompt_token_count"))
        output_tokens = _safe_int(_maybe_get(raw_usage, "candidates_token_count", "output_token_count"))
        total_tokens = _safe_int(_maybe_get(raw_usage, "total_token_count")) or (input_tokens + output_tokens)
    elif provider == "bedrock":
        input_tokens = _safe_int(_maybe_get(raw_usage, "inputTokens", "input_tokens"))
        output_tokens = _safe_int(_maybe_get(raw_usage, "outputTokens", "output_tokens"))
        total_tokens = _safe_int(_maybe_get(raw_usage, "totalTokens", "total_tokens")) or (input_tokens + output_tokens)
    else:
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

    pricing = _pricing_for(provider, model)
    price_key = f"{provider}:{model}"

    if pricing:
        cost_usd = (
            (input_tokens / 1_000_000.0) * pricing["input_per_1m"]
            + (output_tokens / 1_000_000.0) * pricing["output_per_1m"]
        )
        pricing_found = True
    else:
        cost_usd = 0.0
        pricing_found = False

    return {
        "provider": provider,
        "model": model,
        "operation": operation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 8),
        "pricing_found": pricing_found,
        "pricing_key": price_key,
    }


def summarize_usage(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    materialized = [record for record in records if isinstance(record, dict)]
    unpriced_models = sorted(
        {
            record["pricing_key"]
            for record in materialized
            if record.get("total_tokens", 0) > 0 and not record.get("pricing_found", False)
        }
    )

    return {
        "input_tokens": sum(record.get("input_tokens", 0) for record in materialized),
        "output_tokens": sum(record.get("output_tokens", 0) for record in materialized),
        "total_tokens": sum(record.get("total_tokens", 0) for record in materialized),
        "cost_usd": round(sum(record.get("cost_usd", 0.0) for record in materialized), 8),
        "pricing_complete": not unpriced_models,
        "unpriced_models": unpriced_models,
        "records": materialized,
    }


def _extract_usage_records(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []

    if isinstance(payload, list):
        records: List[Dict[str, Any]] = []
        for item in payload:
            records.extend(_extract_usage_records(item))
        return records

    if not isinstance(payload, dict):
        return []

    if "records" in payload and isinstance(payload["records"], list):
        return [item for item in payload["records"] if isinstance(item, dict)]

    required = {"provider", "model", "operation"}
    if required.issubset(payload.keys()):
        return [payload]

    return []


def merge_usage_payloads(*payloads: Any) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for payload in payloads:
        records.extend(_extract_usage_records(payload))
    return summarize_usage(records)
