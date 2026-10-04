from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import re
from pathlib import Path
from typing import Any

from Airlock.core.action import Action
from Airlock.core.policy import DecisionStatus, Policy, Rule
from Airlock.core.shell import network_hosts


DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "policies" / "airlock.yaml"


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    effect: DecisionStatus
    score: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "effect": self.effect.value,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Decision:
    status: DecisionStatus
    risk: int
    reasons: tuple[str, ...]
    matched_rules: tuple[RuleMatch, ...] = ()
    action_id: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.status.value,
            "risk_score": self.risk,
            "reasons": list(self.reasons),
            "matched_rules": [item.to_dict() for item in self.matched_rules],
            "action_id": self.action_id,
        }


class PolicyEngine:
    def __init__(self, policy: Policy):
        self.policy = policy

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_POLICY) -> "PolicyEngine":
        return cls(Policy.load(path))

    def evaluate(self, action: Action) -> Decision:
        matches = tuple(
            RuleMatch(rule.id, rule.effect, rule.score, rule.description)
            for rule in self.policy.rules
            if self._matches(rule, action)
        )
        risk = min(999, sum(item.score for item in matches))

        # A zero score is the policy's explicit signal that an action is safe
        # enough to proceed without interrupting the user. This also covers
        # ordinary commands that do not need a dedicated allow rule.
        if risk == 0:
            status = DecisionStatus.ALLOW
        elif any(item.effect is DecisionStatus.BLOCK for item in matches) or risk >= self.policy.block_threshold:
            status = DecisionStatus.BLOCK
        elif (
            any(item.effect is DecisionStatus.REQUIRE_APPROVAL for item in matches)
            or risk >= self.policy.approval_threshold
        ):
            status = DecisionStatus.REQUIRE_APPROVAL
        elif any(item.effect is DecisionStatus.ALLOW for item in matches):
            status = DecisionStatus.ALLOW
        else:
            status = self.policy.unknown_action

        relevant = matches
        if status in {DecisionStatus.BLOCK, DecisionStatus.REQUIRE_APPROVAL}:
            relevant = tuple(item for item in matches if item.effect is not DecisionStatus.ALLOW)
        reasons = tuple(item.reason for item in relevant) or (
            "No explicit policy rule matched this action",
        )
        return Decision(status, risk, reasons, matches, action.id)

    def _matches(self, rule: Rule, action: Action) -> bool:
        checks = {
            "operation": lambda value: action.operation == value,
            "operation_in": lambda value: action.operation in value,
            "tool": lambda value: action.tool_name == value,
            "tool_in": lambda value: action.tool_name in value,
            "provider": lambda value: action.agent == value,
            "provider_in": lambda value: action.agent in value,
            "environment": lambda value: action.environment == value,
            "environment_in": lambda value: action.environment in value,
            "fact": lambda value: value in action.facts,
            "facts_any": lambda value: bool(action.facts.intersection(value)),
            "facts_all": lambda value: set(value).issubset(action.facts),
            "path": lambda value: _any_path_matches(action.all_paths, _as_list(value)),
            "paths_any": lambda value: _any_path_matches(action.all_paths, _as_list(value)),
            "path_count_gt": lambda value: len(action.all_paths) > int(value),
            "command_regex": lambda value: bool(
                action.command and re.search(str(value), action.command, re.IGNORECASE)
            ),
            "executable": lambda value: any(
                item.executable == value for item in action.shell_invocations
            ),
            "executable_in": lambda value: any(
                item.executable in value for item in action.shell_invocations
            ),
            "subcommand_in": lambda value: any(
                item.arguments and item.arguments[0].lower() in value
                for item in action.shell_invocations
            ),
            "arguments_contain": lambda value: any(
                {str(expected).lower() for expected in value}.issubset(
                    {argument.lower() for argument in item.arguments}
                )
                for item in action.shell_invocations
            ),
            "url_host_in": lambda value: bool(set(network_hosts(action.urls)).intersection(value)),
            "url_host_not_in": lambda value: bool(action.urls)
            and not set(network_hosts(action.urls)).issubset(set(value)),
        }
        for key, expected in rule.match.items():
            check = checks.get(key)
            if check is None:
                raise ValueError(f"rule {rule.id} uses unsupported matcher: {key}")
            if not check(expected):
                return False
        return True


def evaluate(action: Action, policy_path: str | Path = DEFAULT_POLICY) -> Decision:
    """Compatibility entry point for the original prototype."""
    return PolicyEngine.from_file(policy_path).evaluate(action)


def load_policy(path: str | Path = DEFAULT_POLICY) -> Policy:
    return Policy.load(path)


def _as_list(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else [str(item) for item in value]


def _any_path_matches(paths: tuple[str, ...], patterns: list[str]) -> bool:
    for path in paths:
        normalized = path[2:] if path.startswith("./") else path
        basename = normalized.rsplit("/", 1)[-1]
        for pattern in patterns:
            candidate = pattern[2:] if pattern.startswith("./") else pattern
            if fnmatch.fnmatch(normalized, candidate):
                return True
            if "/" not in candidate and fnmatch.fnmatch(basename, candidate):
                return True
            if candidate.startswith("**/") and fnmatch.fnmatch(normalized, candidate[3:]):
                return True
    return False
