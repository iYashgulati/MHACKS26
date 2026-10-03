from typing import Any

from Airlock.adapters.base import ProviderAdapter, decision_reason, extract_common
from Airlock.core.action import Action
from Airlock.core.evaluator import Decision
from Airlock.core.policy import DecisionStatus


class GeminiAdapter(ProviderAdapter):
    provider = "gemini"

    def extract(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return extract_common(payload, ("tool_name", "tool"), ("tool_input", "args"))

    def hook_response(self, decision: Decision) -> dict[str, Any]:
        return {
            "decision": "allow" if decision.status is DecisionStatus.ALLOW else "deny",
            "reason": decision_reason(decision),
        }


def normalize_gemini(data: dict[str, Any]) -> Action:
    return GeminiAdapter().normalize(data)
