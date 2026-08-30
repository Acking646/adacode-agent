from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MemoryCard:
    id: str
    type: str
    scope: str
    content: str
    evidence: str = ""
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.cards: List[MemoryCard] = []
        if path and path.exists():
            self.load()

    def load(self) -> None:
        if not self.path:
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.cards = [MemoryCard(**item) for item in payload.get("cards", [])]

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"cards": [asdict(c) for c in self.cards]}, indent=2), encoding="utf-8")

    def add(self, type: str, scope: str, content: str, evidence: str = "", **metadata: Any) -> MemoryCard:
        card = MemoryCard(
            id=f"mem_{len(self.cards) + 1:04d}",
            type=type,
            scope=scope,
            content=content,
            evidence=evidence,
            metadata=metadata,
        )
        self.cards.append(card)
        self.save()
        return card

    def update(self, card_id: str, **fields: Any) -> Optional[MemoryCard]:
        card = self.get(card_id)
        if not card:
            return None
        for key, value in fields.items():
            if hasattr(card, key):
                setattr(card, key, value)
        self.save()
        return card

    def mark_obsolete(self, card_id: str, reason: str = "") -> None:
        card = self.update(card_id, status="obsolete")
        if card and reason:
            card.metadata["obsolete_reason"] = reason
            self.save()

    def get(self, card_id: str) -> Optional[MemoryCard]:
        return next((card for card in self.cards if card.id == card_id), None)

    def active(self) -> List[MemoryCard]:
        return [card for card in self.cards if card.status == "active"]

    def retrieve(self, query: str, limit: int = 8) -> List[MemoryCard]:
        terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", query.lower()))

        def score(card: MemoryCard) -> Tuple[int, int]:
            haystack = f"{card.type} {card.scope} {card.content} {card.evidence}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            active_bonus = 2 if card.status == "active" else 0
            return overlap + active_bonus, -len(card.content)

        return sorted(self.cards, key=score, reverse=True)[:limit]


def extract_failure_memories(output: str) -> List[Dict[str, str]]:
    """Extract lightweight memory candidates from test output."""

    memories: List[Dict[str, str]] = []
    failed = re.findall(r"FAILED\s+([^\s]+)", output)
    for item in failed[:5]:
        memories.append(
            {
                "type": "test_failure",
                "scope": item,
                "content": f"Test failure observed: {item}",
                "evidence": output[:1000],
            }
        )

    traceback_file = re.findall(r'File "([^"]+)", line (\d+)', output)
    for file_path, line in traceback_file[:5]:
        memories.append(
            {
                "type": "stack_trace",
                "scope": f"{file_path}:{line}",
                "content": f"Stack trace points to {file_path}:{line}.",
                "evidence": output[:1000],
            }
        )
    return memories
