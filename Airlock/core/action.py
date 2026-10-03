from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    agent: str
    operation: str

    command: Optional[str] = None
    path: Optional[str] = None
    paths: list[str] = field(default_factory=list)

    tool_name: Optional[str] = None