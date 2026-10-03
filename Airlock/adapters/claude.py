from core.action import Action


def normalize_claude(data: dict) -> Action:

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {})

    if tool_name == "Bash":
        return Action(
            agent="claude",
            operation="shell",
            command=tool_input.get("command", ""),
            tool_name=tool_name
        )

    if tool_name in ["Write", "Edit"]:
        return Action(
            agent="claude",
            operation="write_file",
            path=tool_input.get("file_path", ""),
            tool_name=tool_name
        )

    if tool_name == "Read":
        return Action(
            agent="claude",
            operation="read_file",
            path=tool_input.get("file_path", ""),
            tool_name=tool_name
        )

    return Action(
        agent="claude",
        operation="unknown",
        tool_name=tool_name
    )