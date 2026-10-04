from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Sequence

import requests

from Airlock.completion import _significance, collect_diff
from Airlock.hook.photon_approval import PHOTON_BASE


def _transcript_assistant_message(path: object) -> str:
    """Recover the final response for Claude versions that omit it at Stop."""
    if not isinstance(path, str) or not path:
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]
        for entry in reversed(entries):
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            if isinstance(content, str):
                return content.strip()[:4000]
            if isinstance(content, list):
                text = "\n".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ).strip()
                if text:
                    return text[:4000]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return ""


def completion_payload(hook_input: dict[str, Any]) -> dict[str, Any] | None:
    event = str(hook_input.get("hook_event_name", "Stop"))

    # A Stop can occur while a background task is still running. A later Stop
    # will report actual completion, so do not send a misleading "done" text.
    if event == "Stop" and hook_input.get("background_tasks"):
        return None

    cwd = hook_input.get("cwd")
    root = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    diff = collect_diff(root)
    significance, reasons = _significance(diff.added, diff.removed, list(diff.files))

    assistant_message = str(hook_input.get("last_assistant_message", "")).strip()
    if not assistant_message:
        assistant_message = _transcript_assistant_message(hook_input.get("transcript_path"))

    payload: dict[str, Any] = {
        "event": event,
        "sessionId": str(hook_input.get("session_id", "")),
        "assistantMessage": assistant_message[:4000],
        "significance": significance,
        "reasons": reasons,
        "added": diff.added,
        "removed": diff.removed,
        "files": list(diff.files),
        "diffstat": diff.diffstat,
    }
    if event == "StopFailure":
        payload["error"] = str(hook_input.get("error", "unknown"))
        payload["errorDetails"] = str(hook_input.get("error_details", ""))[:1000]
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    try:
        hook_input = json.load(sys.stdin)
        if not isinstance(hook_input, dict):
            return 0
        payload = completion_payload(hook_input)
        if payload is not None:
            requests.post(f"{PHOTON_BASE}/completion", json=payload, timeout=20)
    except Exception as error:
        # Completion notifications are observational. They must never prevent
        # Claude from finishing a turn.
        print(f"Airlock completion notification failed: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
