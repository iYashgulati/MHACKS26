from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
import sys

from Airlock.core.action import Action
from Airlock.core.evaluator import Decision


class ApprovalResolution(StrEnum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class ApprovalProvider(ABC):
    @abstractmethod
    def request(self, action: Action, decision: Decision) -> ApprovalResolution:
        raise NotImplementedError


class TerminalApprovalProvider(ApprovalProvider):
    """Local stand-in for Photon that does not consume hook JSON from stdin."""

    def request(self, action: Action, decision: Decision) -> ApprovalResolution:
        summary = action.command or ", ".join(action.all_paths) or action.tool_name or "unknown"
        message = (
            "\nAIRLOCK APPROVAL\n"
            f"Action: {summary}\n"
            f"Risk: {decision.risk}\n"
            f"Reasons: {'; '.join(decision.reasons)}\n"
            "Approve? [y/N] "
        )
        try:
            with open("/dev/tty", "r+", encoding="utf-8") as terminal:
                terminal.write(message)
                terminal.flush()
                response = terminal.readline().strip().lower()
        except OSError:
            print("Airlock could not open /dev/tty; denying approval", file=sys.stderr)
            return ApprovalResolution.DENIED
        return (
            ApprovalResolution.APPROVED
            if response in {"y", "yes", "approve"}
            else ApprovalResolution.DENIED
        )
