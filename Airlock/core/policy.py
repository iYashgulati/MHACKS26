from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class DecisionStatus(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    effect: DecisionStatus
    score: int = 0
    match: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Policy:
    rules: tuple[Rule, ...]
    unknown_action: DecisionStatus = DecisionStatus.REQUIRE_APPROVAL
    hook_failure: DecisionStatus = DecisionStatus.BLOCK
    approval_threshold: int = 30
    block_threshold: int = 100
    approval_timeout_seconds: int = 120

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("policy must be a mapping declaring version: 1")

        defaults = data.get("defaults", {})
        thresholds = data.get("thresholds", {})
        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ValueError("policy rules must be a list")

        rules: list[Rule] = []
        seen: set[str] = set()
        for item in raw_rules:
            if not isinstance(item, dict):
                raise ValueError("every policy rule must be a mapping")
            rule_id = item.get("id")
            if not isinstance(rule_id, str) or not rule_id:
                raise ValueError("every policy rule requires an id")
            if rule_id in seen:
                raise ValueError(f"duplicate policy rule id: {rule_id}")
            seen.add(rule_id)
            score = item.get("score", 0)
            matcher = item.get("match")
            if not isinstance(score, int) or score < 0:
                raise ValueError(f"rule {rule_id} score must be a non-negative integer")
            if not isinstance(matcher, dict) or not matcher:
                raise ValueError(f"rule {rule_id} requires a non-empty match mapping")
            rules.append(
                Rule(
                    id=rule_id,
                    description=str(item.get("description") or rule_id.replace("-", " ")),
                    effect=_status(item.get("effect"), f"rule {rule_id} effect"),
                    score=score,
                    match=matcher,
                )
            )

        approval = thresholds.get("require_approval", 30)
        block = thresholds.get("block", 100)
        if not isinstance(approval, int) or not isinstance(block, int) or block <= approval:
            raise ValueError("block threshold must be an integer greater than approval threshold")
        return cls(
            rules=tuple(rules),
            unknown_action=_status(defaults.get("unknown_action", "require_approval"), "defaults.unknown_action"),
            hook_failure=_status(defaults.get("hook_failure", "block"), "defaults.hook_failure"),
            approval_threshold=approval,
            block_threshold=block,
            approval_timeout_seconds=int(defaults.get("approval_timeout_seconds", 120)),
        )


def _status(value: object, location: str) -> DecisionStatus:
    try:
        return DecisionStatus(str(value).upper())
    except ValueError as error:
        raise ValueError(f"invalid decision at {location}: {value}") from error
