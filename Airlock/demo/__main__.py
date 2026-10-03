from __future__ import annotations

import json

from Airlock.adapters import get_adapter
from Airlock.core.evaluator import PolicyEngine


SCENARIOS = (
    (
        "ALLOW: inspect repository",
        "claude",
        {"tool_name": "Bash", "tool_input": {"command": "git status"}},
    ),
    (
        "REQUIRE_APPROVAL: install dependency",
        "gemini",
        {"tool": "run_shell_command", "args": {"cmd": "npm install jsonwebtoken"}},
    ),
    (
        "BLOCK: read secret",
        "codex",
        {"tool_name": "Read", "tool_input": {"file_path": ".env"}},
    ),
    (
        "BLOCK: force push",
        "claude",
        {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}},
    ),
)


def main() -> None:
    engine = PolicyEngine.from_file()
    for label, provider, payload in SCENARIOS:
        action = get_adapter(provider).normalize(payload)
        decision = engine.evaluate(action)
        print(f"\n{label}")
        print(json.dumps(decision.to_dict(), indent=2))


if __name__ == "__main__":
    main()
