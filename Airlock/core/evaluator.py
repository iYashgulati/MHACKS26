from dataclasses import dataclass
import yaml


@dataclass
class Decision:
    status: str
    risk: int
    reasons: list[str]


def load_policy():
    with open("policies/airlock.yaml", "r") as file:
        return yaml.safe_load(file)


def evaluate(action):
    policy = load_policy()

    risk = 0
    reasons = []

    if action.operation == "shell":

        command = action.command or ""

        for blocked in policy["blocked_commands"]:
            if blocked in command:
                risk += 100
                reasons.append(
                    f"Blocked command detected: {blocked}"
                )

        for approval in policy["approval_commands"]:
            if approval in command:
                risk += 30
                reasons.append(
                    f"Sensitive command detected: {approval}"
                )
            
    if action.path:

        for protected in policy["protected_paths"]:
            if protected in action.path:
                risk += 100
                reasons.append(
                    f"Protected path accessed: {protected}"
                )

    if risk >= policy["risk_thresholds"]["block"]:
        return Decision(
            status="BLOCK",
            risk=risk,
            reasons=reasons
        )

    if risk >= policy["risk_thresholds"]["approval"]:
        return Decision(
            status="APPROVAL",
            risk=risk,
            reasons=reasons
        )

    return Decision(
        status="ALLOW",
        risk=risk,
        reasons=reasons
    )