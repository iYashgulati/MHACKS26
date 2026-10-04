from __future__ import annotations

import json
import sys

import requests

from Airlock.core.action import Action
from Airlock.core.evaluator import Decision
from Airlock.hook.approval import ApprovalProvider, ApprovalResolution


PHOTON_BASE = "http://localhost:8787"
REQUEST_TIMEOUT = 630


def _summarize(action: Action) -> str:
    return (
        action.command
        or ", ".join(action.all_paths)
        or action.tool_name
        or "unknown action"
    )


def _last_user_message(path: str | None) -> str:
    """Pull the user's original instruction out of the Claude Code transcript."""
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]
        for entry in reversed(entries):
            if entry.get("type") == "user":
                return str(entry.get("message", {}).get("content", ""))[:400]
    except Exception:
        pass
    return ""


def notify_blocked(action: Action, decision: Decision) -> None:
    """Fire-and-forget notice that something was blocked outright."""
    try:
        requests.post(
            f"{PHOTON_BASE}/notify",
            json={
                "action": _summarize(action),
                "reason": f"Risk score {decision.risk}. " + "; ".join(decision.reasons),
            },
            timeout=3,
        )
    except Exception:
        pass  # a notification failure must never change the block


class PhotonApprovalProvider(ApprovalProvider):
    """Routes approval requests to the Spectrum service, which texts the user."""

    def __init__(self, url: str = f"{PHOTON_BASE}/approval", timeout: int = REQUEST_TIMEOUT):
        self.url = url
        self.timeout = timeout

    def request(self, action: Action, decision: Decision) -> ApprovalResolution:
        payload = {
            "action": _summarize(action),
            "reason": f"Risk score {decision.risk}. " + "; ".join(decision.reasons),
            "task": _last_user_message(action.raw_input.get("transcript_path")),
        }

        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            result = response.json().get("decision")
        except Exception as error:
            print(f"Airlock could not reach Photon service: {error}", file=sys.stderr)
            return ApprovalResolution.DENIED

        if result == "allow":
            return ApprovalResolution.APPROVED
        if result == "expired":
            return ApprovalResolution.EXPIRED
        return ApprovalResolution.DENIED
