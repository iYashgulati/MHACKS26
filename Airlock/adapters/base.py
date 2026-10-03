from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from Airlock.core.action import Action
from Airlock.core.evaluator import Decision
from Airlock.core.shell import analyze_shell, extract_patch_paths, extract_urls


SHELL_TOOLS = {"bash", "shell", "run_shell_command", "exec_command"}
READ_TOOLS = {"read", "read_file", "read_many_files"}
WRITE_TOOLS = {"write", "write_file", "edit", "replace", "apply_patch"}
LIST_TOOLS = {"glob", "ls", "list_files", "list_directory", "search_file_content"}
NETWORK_TOOLS = {"webfetch", "web_fetch", "fetch", "http_request"}


class AdapterError(ValueError):
    pass


class ProviderAdapter(ABC):
    provider: str

    @abstractmethod
    def extract(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def hook_response(self, decision: Decision) -> dict[str, Any]:
        raise NotImplementedError

    def normalize(self, payload: dict[str, Any]) -> Action:
        tool, tool_input = self.extract(payload)
        tool_key = tool.lower()
        command = first_string(tool_input, "command", "cmd", "script")
        paths = set(extract_paths(tool_input))
        urls: set[str] = set()
        facts: set[str] = set()
        invocations = ()

        if tool_key in SHELL_TOOLS or command is not None:
            operation = "shell"
            if command is None:
                raise AdapterError(f"{tool} requires a string command")
            invocations, shell_paths, shell_urls, shell_facts = analyze_shell(command)
            paths.update(shell_paths)
            urls.update(shell_urls)
            facts.update(shell_facts)
        elif tool_key in READ_TOOLS:
            operation = "read"
        elif tool_key in WRITE_TOOLS:
            operation = "write"
            if tool_key == "apply_patch":
                patch = first_string(tool_input, "patch", "input") or ""
                paths.update(extract_patch_paths(patch))
        elif tool_key in LIST_TOOLS:
            operation = "list"
        elif tool_key in NETWORK_TOOLS:
            operation = "network"
        else:
            operation = "unknown"
            facts.add("unknown_tool")

        for value in tool_input.values():
            urls.update(extract_urls(value))
        if urls:
            facts.add("external_network")

        sorted_paths = tuple(sorted(paths))
        return Action(
            agent=self.provider,
            operation=operation,
            command=command,
            path=sorted_paths[0] if len(sorted_paths) == 1 else None,
            paths=sorted_paths,
            tool_name=tool,
            urls=tuple(sorted(urls)),
            environment=first_string(tool_input, "environment", "env", "target_environment"),
            session_id=first_string(payload, "session_id", "thread_id"),
            cwd=first_string(payload, "cwd", "working_directory"),
            facts=frozenset(facts),
            shell_invocations=invocations,
            raw_input=payload,
            idempotency_key=_idempotency_key(self.provider, payload),
        )


def extract_common(
    payload: dict[str, Any],
    tool_keys: tuple[str, ...],
    input_keys: tuple[str, ...],
) -> tuple[str, dict[str, Any]]:
    tool = first_string(payload, *tool_keys)
    if not tool:
        raise AdapterError(f"missing tool name; expected one of: {', '.join(tool_keys)}")
    tool_input: object = None
    for key in input_keys:
        if key in payload:
            tool_input = payload[key]
            break
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        raise AdapterError("tool input must be a JSON object")
    return tool, tool_input


def extract_paths(tool_input: dict[str, Any]) -> tuple[str, ...]:
    paths: set[str] = set()
    for key in ("path", "file_path", "absolute_path", "directory", "dir_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.add(normalize_path(value))
    value = tool_input.get("paths")
    if isinstance(value, list):
        paths.update(normalize_path(item) for item in value if isinstance(item, str))
    return tuple(sorted(paths))


def normalize_path(value: str) -> str:
    value = value.replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    try:
        return str(PurePosixPath(value))
    except ValueError:
        return value


def first_string(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def decision_reason(decision: Decision) -> str:
    prefix = {
        "ALLOW": "Allowed by Airlock",
        "REQUIRE_APPROVAL": "Airlock approval required; action was not executed",
        "BLOCK": "Blocked by Airlock",
    }[decision.status.value]
    return f"{prefix}: {'; '.join(decision.reasons)}"


def _idempotency_key(provider: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"provider": provider, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "idem_" + hashlib.sha256(canonical).hexdigest()[:32]
