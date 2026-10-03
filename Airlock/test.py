from adapters.claude import normalize_claude
from core.evaluator import evaluate

fake_request = {
    "tool_name": "Bash",
    "tool_input": {
       "command": "ls"
    }
}

action = normalize_claude(fake_request)

print("ACTION:")
print(action)

decision = evaluate(action)

print("\nDECISION:")
print(decision)