from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from Airlock.core.action import Action
from Airlock.core.evaluator import Decision


class JsonlAuditLog:
    """Append-only local audit repository; never stores raw tool input."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, action: Action, decision: Decision, resolution: str | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action.to_dict(include_raw=False),
            **decision.to_dict(),
            "resolution": resolution,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
