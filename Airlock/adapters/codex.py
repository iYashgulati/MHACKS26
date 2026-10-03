from typing import Any

from Airlock.adapters.base import ProviderAdapter, decision_reason, extract_common
from Airlock.core.action import Action
from Airlock.core.evaluator import Decision
from Airlock.core.policy import DecisionStatus


class CodexAdapter(ProviderAdapter):
    provider = "codex"

    def extract(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return extract_common(payload, ("tool_name", "type"), ("tool_input", "input"))

    def hook_response(self, decision: Decision) -> dict[str, Any]:
        permission = "allow" if decision.status is DecisionStatus.ALLOW else "deny"
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": permission,
                "permissionDecisionReason": decision_reason(decision),
            }
        }


def normalize_codex(data: dict[str, Any]) -> Action:
    return CodexAdapter().normalize(data)
