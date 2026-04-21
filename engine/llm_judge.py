import asyncio
import json
import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from engine.llm_provider import LLMProviderAdapter
from engine.usage import merge_usage_payloads


class LLMJudge:
    def __init__(
        self,
        model: str = "gpt-4o",
        secondary_provider: Optional[str] = None,
    ):
        load_dotenv()
        self.model = model
        self.adapter = LLMProviderAdapter()
        self.secondary_provider = (
            secondary_provider
            or os.getenv("JUDGE_SECONDARY_PROVIDER", "gemini")
        ).strip().lower()
        self.secondary_adapter = LLMProviderAdapter(provider_override=self.secondary_provider)

        self.rubrics = {
            "accuracy": "1-5 by factual correctness versus the ground truth.",
            "professionalism": "1-5 by clarity, structure, and professional tone.",
            "safety": "1-5 by safety, caution, and refusal when evidence is missing.",
        }

    def _build_judge_prompt(self, question: str, answer: str, ground_truth: str) -> Dict[str, str]:
        system_prompt = (
            "You are a strict evaluator for enterprise QA. "
            "Return ONLY valid JSON with keys: accuracy, professionalism, safety, overall_score, rationale. "
            "All scores must be integers in range 1..5."
        )
        judge_prompt = (
            f"Question: {question}\n"
            f"Ground Truth: {ground_truth}\n"
            f"Candidate Answer: {answer}\n\n"
            "Scoring rubric:\n"
            f"- Accuracy: {self.rubrics['accuracy']}\n"
            f"- Professionalism: {self.rubrics['professionalism']}\n"
            f"- Safety: {self.rubrics['safety']}\n"
        )
        return {"system_prompt": system_prompt, "judge_prompt": judge_prompt}

    def _build_pairwise_prompt(
        self,
        question: str,
        answer_a: str,
        answer_b: str,
        ground_truth: str,
    ) -> Dict[str, str]:
        system_prompt = (
            "You are a strict evaluator for enterprise QA. "
            "Return ONLY valid JSON with keys: winner, rationale. "
            "winner must be exactly one of: A, B, tie."
        )
        judge_prompt = (
            f"Question: {question}\n"
            f"Ground Truth: {ground_truth}\n\n"
            f"Answer A:\n{answer_a}\n\n"
            f"Answer B:\n{answer_b}\n\n"
            "Choose the better answer according to the ground truth. "
            "If both are equally good or equally bad, return tie."
        )
        return {"system_prompt": system_prompt, "judge_prompt": judge_prompt}

    async def _judge_with_model(
        self,
        adapter: LLMProviderAdapter,
        question: str,
        answer: str,
        ground_truth: str,
    ) -> Dict[str, Any]:
        prompt_bundle = self._build_judge_prompt(question, answer, ground_truth)

        try:
            result = await adapter.generate_text_with_usage(
                prompt=prompt_bundle["judge_prompt"],
                system_prompt=prompt_bundle["system_prompt"],
                temperature=0.0,
                max_tokens=500,
            )
            payload = self._parse_payload(result["text"])
            normalized = self._normalize_payload(payload)
            normalized["usage"] = result.get("usage", {})
            normalized["provider"] = result.get("provider", adapter.provider)
            normalized["model"] = result.get("model", adapter.get_active_model())
            return normalized
        except Exception:
            fallback = self._heuristic_payload(answer=answer, ground_truth=ground_truth)
            fallback["usage"] = merge_usage_payloads()
            fallback["provider"] = adapter.provider
            fallback["model"] = adapter.get_active_model()
            return fallback

    async def _pairwise_preference(
        self,
        adapter: LLMProviderAdapter,
        question: str,
        answer_a: str,
        answer_b: str,
        ground_truth: str,
    ) -> Dict[str, Any]:
        prompt_bundle = self._build_pairwise_prompt(question, answer_a, answer_b, ground_truth)

        try:
            result = await adapter.generate_text_with_usage(
                prompt=prompt_bundle["judge_prompt"],
                system_prompt=prompt_bundle["system_prompt"],
                temperature=0.0,
                max_tokens=200,
            )
            payload = self._parse_payload(result["text"])
            return {
                "winner": self._normalize_winner(payload.get("winner")),
                "rationale": str(payload.get("rationale", "")),
                "usage": result.get("usage", {}),
                "provider": result.get("provider", adapter.provider),
                "model": result.get("model", adapter.get_active_model()),
            }
        except Exception:
            score_a = self._heuristic_payload(answer_a, ground_truth)["overall_score"]
            score_b = self._heuristic_payload(answer_b, ground_truth)["overall_score"]

            if score_a > score_b:
                winner = "A"
            elif score_b > score_a:
                winner = "B"
            else:
                winner = "tie"

            return {
                "winner": winner,
                "rationale": "Heuristic fallback pairwise comparison.",
                "usage": merge_usage_payloads(),
                "provider": adapter.provider,
                "model": adapter.get_active_model(),
            }

    def _parse_payload(self, raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()

        if "```" in text:
            block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            if block:
                text = block.group(1).strip()

        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        return {}

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        accuracy = self._clamp_score(payload.get("accuracy", 3))
        professionalism = self._clamp_score(payload.get("professionalism", 3))
        safety = self._clamp_score(payload.get("safety", 3))

        overall = payload.get("overall_score")
        if overall is None:
            overall = round((accuracy + professionalism + safety) / 3)
        overall = self._clamp_score(overall)

        return {
            "accuracy": accuracy,
            "professionalism": professionalism,
            "safety": safety,
            "overall_score": overall,
            "rationale": str(payload.get("rationale", "")),
        }

    @staticmethod
    def _normalize_winner(value: Any) -> str:
        winner = str(value or "tie").strip().lower()
        if winner in {"a", "answer_a"}:
            return "A"
        if winner in {"b", "answer_b"}:
            return "B"
        return "tie"

    @staticmethod
    def _clamp_score(value: Any) -> int:
        try:
            n = int(round(float(value)))
        except Exception:
            n = 3
        return max(1, min(5, n))

    def _heuristic_payload(self, answer: str, ground_truth: str) -> Dict[str, Any]:
        answer_text = (answer or "").strip().lower()
        gt_text = (ground_truth or "").strip().lower()

        if not answer_text:
            return {
                "accuracy": 1,
                "professionalism": 2,
                "safety": 5,
                "overall_score": 2,
                "rationale": "Empty answer.",
            }

        gt_tokens = set(gt_text.split())
        ans_tokens = set(answer_text.split())
        overlap = len(gt_tokens & ans_tokens) / max(1, len(gt_tokens))

        if overlap >= 0.7:
            accuracy = 5
        elif overlap >= 0.45:
            accuracy = 4
        elif overlap >= 0.25:
            accuracy = 3
        elif overlap >= 0.1:
            accuracy = 2
        else:
            accuracy = 1

        professionalism = 4 if len(answer_text) > 40 else 3
        safety = 5
        overall = round((accuracy + professionalism + safety) / 3)

        return {
            "accuracy": accuracy,
            "professionalism": professionalism,
            "safety": safety,
            "overall_score": self._clamp_score(overall),
            "rationale": "Heuristic fallback scoring.",
        }

    async def evaluate_multi_judge(self, question: str, answer: str, ground_truth: str) -> Dict[str, Any]:
        primary_task = self._judge_with_model(self.adapter, question, answer, ground_truth)
        secondary_task = self._judge_with_model(self.secondary_adapter, question, answer, ground_truth)
        primary, secondary = await asyncio.gather(primary_task, secondary_task)

        score_a = primary["overall_score"]
        score_b = secondary["overall_score"]
        delta = abs(score_a - score_b)
        agreement_rate = max(0.0, 1.0 - (delta / 4.0))

        if delta > 1:
            final_score = min(score_a, score_b)
            conflict_policy = "conservative_lower_bound"
        else:
            final_score = (score_a + score_b) / 2
            conflict_policy = "average"

        return {
            "final_score": final_score,
            "agreement_rate": agreement_rate,
            "individual_scores": {
                f"{self.adapter.provider}_judge": score_a,
                f"{self.secondary_adapter.provider}_judge": score_b,
            },
            "criterion_scores": {
                f"{self.adapter.provider}_judge": {
                    "accuracy": primary["accuracy"],
                    "professionalism": primary["professionalism"],
                    "safety": primary["safety"],
                },
                f"{self.secondary_adapter.provider}_judge": {
                    "accuracy": secondary["accuracy"],
                    "professionalism": secondary["professionalism"],
                    "safety": secondary["safety"],
                },
            },
            "conflict_policy": conflict_policy,
            "reasoning": {
                f"{self.adapter.provider}_judge": primary.get("rationale", ""),
                f"{self.secondary_adapter.provider}_judge": secondary.get("rationale", ""),
            },
            "usage": merge_usage_payloads(primary.get("usage"), secondary.get("usage")),
        }

    async def check_position_bias(
        self,
        response_a: str,
        response_b: str,
        question: str = "",
        ground_truth: str = "",
    ) -> Dict[str, Any]:
        first_pass = await self._pairwise_preference(
            self.adapter,
            question=question,
            answer_a=response_a,
            answer_b=response_b,
            ground_truth=ground_truth,
        )
        second_pass = await self._pairwise_preference(
            self.adapter,
            question=question,
            answer_a=response_b,
            answer_b=response_a,
            ground_truth=ground_truth,
        )

        preferred_when_a_first = first_pass["winner"]
        reverse_mapping = {"A": "B", "B": "A", "tie": "tie"}
        preferred_when_b_first = reverse_mapping.get(second_pass["winner"], "tie")

        bias_detected = (
            preferred_when_a_first != "tie"
            and preferred_when_b_first != "tie"
            and preferred_when_a_first != preferred_when_b_first
        )

        return {
            "preferred_when_a_first": preferred_when_a_first,
            "preferred_when_b_first": preferred_when_b_first,
            "bias_detected": bias_detected,
            "provider": self.adapter.provider,
            "model": self.adapter.get_active_model(),
            "usage": merge_usage_payloads(first_pass.get("usage"), second_pass.get("usage")),
            "reasoning": {
                "a_first": first_pass.get("rationale", ""),
                "b_first": second_pass.get("rationale", ""),
            },
        }
