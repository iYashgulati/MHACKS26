from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ShellInvocation:
    executable: str
    arguments: tuple[str, ...]
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "executable": self.executable,
            "arguments": list(self.arguments),
            "raw": self.raw,
        }


@dataclass(frozen=True)
class Action:
    """Provider-neutral representation of a proposed agent operation."""

    agent: str
    operation: str
    command: str | None = None
    path: str | None = None
    paths: tuple[str, ...] = ()
    tool_name: str | None = None
    urls: tuple[str, ...] = ()
    environment: str | None = None
    session_id: str | None = None
    cwd: str | None = None
    facts: frozenset[str] = frozenset()
    shell_invocations: tuple[ShellInvocation, ...] = ()
    raw_input: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    id: str = field(default_factory=lambda: f"act_{uuid4().hex}")
    idempotency_key: str | None = None

    @property
    def provider(self) -> str:
        return self.agent

    @property
    def all_paths(self) -> tuple[str, ...]:
        values = set(self.paths)
        if self.path:
            values.add(self.path)
        return tuple(sorted(values))

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "idempotency_key": self.idempotency_key,
            "provider": self.agent,
            "session_id": self.session_id,
            "tool": self.tool_name,
            "operation": self.operation,
            "command": self.command,
            "paths": list(self.all_paths),
            "urls": list(self.urls),
            "environment": self.environment,
            "cwd": self.cwd,
            "facts": sorted(self.facts),
            "shell_invocations": [item.to_dict() for item in self.shell_invocations],
        }
        if include_raw:
            result["raw_input"] = self.raw_input
        return result
