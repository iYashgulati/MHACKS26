import sys
import json

from adapters.claude import normalize_claude
from core.evaluator import evaluate


data = json.load(sys.stdin)

action = normalize_claude(data)

decision = evaluate(action)

print(decision)