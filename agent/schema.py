from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


Role = str


@dataclass
class Message:
    id: str
    role: Role
    content: str
    kind: str = "chat"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    thought: str = ""


@dataclass
class ToolResult:
    ok: bool
    output: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextCandidate:
    id: str
    kind: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSelection:
    keep: List[str]
    drop: List[str] = field(default_factory=list)
    update_memory: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
