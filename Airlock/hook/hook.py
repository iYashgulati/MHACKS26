from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Sequence

from Airlock.adapters import AdapterError, get_adapter
from Airlock.core.audit import JsonlAuditLog
from Airlock.core.evaluator import Decision, PolicyEngine
from Airlock.core.policy import DecisionStatus
from Airlock.hook.approval import ApprovalResolution, TerminalApprovalProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = PROJECT_ROOT / "Airlock" / "policies" / "airlock.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an agent tool call with Airlock")
    parser.add_argument("--provider", choices=("claude", "codex", "gemini"), required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", choices=("normalized", "hook"), default="normalized")
    parser.add_argument("--approval", choices=("none", "terminal"), default="none")
    parser.add_argument("--audit-log", type=Path, default=Path(".airlock/audit.jsonl"))
    parser.add_argument("--no-audit", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = get_adapter(args.provider)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise AdapterError("hook input must be a JSON object")
        action = adapter.normalize(payload)
        decision = PolicyEngine.from_file(args.policy).evaluate(action)
        resolution: str | None = None

        if decision.status is DecisionStatus.REQUIRE_APPROVAL and args.approval == "terminal":
            approval = TerminalApprovalProvider().request(action, decision)
            resolution = approval.value
            if approval is ApprovalResolution.APPROVED:
                decision = replace(
                    decision,
                    status=DecisionStatus.ALLOW,
                    reasons=decision.reasons + ("Approved by user through terminal",),
                )
            else:
                decision = replace(
                    decision,
                    status=DecisionStatus.BLOCK,
                    reasons=decision.reasons + ("Denied by user or approval unavailable",),
                )

        if not args.no_audit:
            JsonlAuditLog(args.audit_log).append(action, decision, resolution)

        output = (
            adapter.hook_response(decision)
            if args.output == "hook"
            else {**decision.to_dict(), "action": action.to_dict()}
        )
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        return 0
    except Exception as error:
        # Malformed input, a bad policy, or an internal error must never become an allow.
        fallback = Decision(
            DecisionStatus.BLOCK,
            100,
            (f"Airlock hook failure: {error}",),
        )
        output = adapter.hook_response(fallback) if args.output == "hook" else fallback.to_dict()
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
