from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .memory import MemoryStore
from .schema import ContextCandidate, ContextSelection, Message


class SelectionModel:
    def select(self, task: str, candidates: List[ContextCandidate], token_budget: int) -> ContextSelection:
        """Choose context candidates for the next model call."""


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class RewardWeights:
    task_overlap: float = 1.8
    recency: float = 0.8
    has_error: float = 2.2
    has_file_path: float = 1.2
    has_code: float = 1.0
    active_memory: float = 1.5
    token_cost: float = -0.002
    obsolete: float = -3.0


class RuleBasedSelectionModel:
    def __init__(self, weights: Optional[RewardWeights] = None) -> None:
        self.weights = weights or RewardWeights()

    def select(self, task: str, candidates: List[ContextCandidate], token_budget: int) -> ContextSelection:
        scored = [(self._score(task, idx, candidate), candidate) for idx, candidate in enumerate(candidates)]
        scored.sort(key=lambda item: item[0], reverse=True)

        keep: List[str] = []
        used = 0
        for _, candidate in scored:
            cost = estimate_tokens(candidate.content)
            if used + cost <= token_budget or candidate.kind in {"task", "memory"}:
                keep.append(candidate.id)
                used += cost
        drop = [candidate.id for candidate in candidates if candidate.id not in keep]
        return ContextSelection(keep=keep, drop=drop, reason="规则奖励评分选择了紧凑上下文。")

    def _score(self, task: str, index: int, candidate: ContextCandidate) -> float:
        text = candidate.content.lower()
        terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", task.lower()))
        overlap = sum(1 for term in terms if term in text)
        score = overlap * self.weights.task_overlap
        score += index * self.weights.recency / max(1, index + 1)
        if any(word in text for word in ["error", "failed", "traceback", "pytest", "exception", "失败", "错误"]):
            score += self.weights.has_error
        if re.search(r"[\w./\\-]+\.(py|js|ts|java|cpp|c|go|rs|md)", text):
            score += self.weights.has_file_path
        if "```" in text or re.search(r"\b(def|class|function|import|return)\b", text):
            score += self.weights.has_code
        if candidate.kind == "memory" and candidate.metadata.get("status") == "active":
            score += self.weights.active_memory
        if candidate.metadata.get("status") == "obsolete":
            score += self.weights.obsolete
        score += estimate_tokens(candidate.content) * self.weights.token_cost
        return score


class TrainedJSONSelectionModel:
    """OpenAI-compatible wrapper around a SFT context manager.

    The model is expected to output a JSON object with keep/drop/update_memory.
    This wrapper can point to a local vLLM server serving Qwen3-0.6B after SFT.
    """

    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client

    def select(self, task: str, candidates: List[ContextCandidate], token_budget: int) -> ContextSelection:
        operational_kinds = {"assistant", "tool", "observation", "error", "memory"}
        if not any(candidate.kind in operational_kinds for candidate in candidates):
            return ContextSelection(
                keep=["task_goal"],
                drop=[candidate.id for candidate in candidates if candidate.id != "task_goal"],
                reason="No tool history yet; skipped Qwen compression for the first step.",
            )
        prompt = {
            "instruction": "Select useful context for the next coding-agent step under the token budget.",
            "task": task,
            "token_budget": token_budget,
            "candidates": [
                {
                    "id": c.id,
                    "type": c.kind,
                    "content": c.content,
                    "metadata": c.metadata,
                }
                for c in candidates
            ],
            "schema": {
                "keep": ["candidate_id"],
                "drop": ["candidate_id"],
                "update_memory": [{"id": "mem_id", "status": "active|obsolete", "content": "updated content"}],
                "reason": "short reason",
            },
        }
        response = self.llm_client.complete(
            [
                Message("cm_system", "system", "You are a context manager. Return only valid JSON."),
                Message("cm_user", "user", json.dumps(prompt, ensure_ascii=False)),
            ]
        )
        payload = json.loads(_extract_json(response))
        keep = [str(item) for item in payload.get("keep", [])]
        drop = [str(item) for item in payload.get("drop", [])]
        updates = payload.get("update_memory", [])
        reason = str(payload.get("reason", "SFT manager selected context."))
        return ContextSelection(keep=keep, drop=drop, update_memory=updates if isinstance(updates, list) else [], reason=reason)


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Context manager response does not contain JSON.")
    return text[start : end + 1]


class ContextManager:
    def __init__(
        self,
        memory: MemoryStore,
        selector: Optional[SelectionModel] = None,
        token_budget: int = 3500,
    ) -> None:
        self.memory = memory
        self.selector = selector or RuleBasedSelectionModel()
        self.token_budget = token_budget
        self.last_stats = {}

    def build_candidates(self, task: str, history: List[Message]) -> List[ContextCandidate]:
        candidates = [ContextCandidate("task_goal", "task", task, {"status": "active"})]
        for card in self.memory.retrieve(task, limit=10):
            candidates.append(
                ContextCandidate(
                    card.id,
                    "memory",
                    f"[{card.type}] {card.scope}: {card.content}\nEvidence: {card.evidence[:600]}",
                    {"status": card.status, "scope": card.scope},
                )
            )
        for message in history[-12:]:
            candidates.append(ContextCandidate(message.id, message.kind, message.content, message.metadata))
        return candidates

    def assemble(self, task: str, history: List[Message]) -> Tuple[List[Message], ContextSelection]:
        candidates = self.build_candidates(task, history)
        try:
            selection = self.selector.select(task, candidates, self.token_budget)
        except Exception as exc:
            fallback = RuleBasedSelectionModel()
            selection = fallback.select(task, candidates, self.token_budget)
            selection.reason = f"上下文管理器失败（{type(exc).__name__}: {exc}），已回退到规则评分。"
        by_id = {candidate.id: candidate for candidate in candidates}
        selection = self._pin_operational_context(selection, candidates, by_id)
        selected = [by_id[item] for item in selection.keep if item in by_id]
        full_tokens = sum(estimate_tokens(candidate.content) for candidate in candidates)
        selected_tokens = sum(estimate_tokens(candidate.content) for candidate in selected)
        self.last_stats = {
            "full_tokens": full_tokens,
            "selected_tokens": selected_tokens,
            "compression": round(1.0 - selected_tokens / max(1, full_tokens), 4),
            "candidates": [
                {
                    "id": candidate.id,
                    "kind": candidate.kind,
                    "tokens": estimate_tokens(candidate.content),
                    "metadata": candidate.metadata,
                }
                for candidate in candidates
            ],
        }

        for update in selection.update_memory:
            card_id = update.get("id")
            if card_id:
                self.memory.update(str(card_id), **{k: v for k, v in update.items() if k != "id"})

        content = ["Context selected for the next coding step:"]
        for item in selected:
            content.append(f"\n[{item.id} | {item.kind}]\n{item.content}")
        content.append(f"\nSelection reason: {selection.reason}")

        messages = [
            Message("system_prompt", "system", CODING_SYSTEM_PROMPT),
            Message("managed_context", "user", "\n".join(content), "managed_context"),
        ]
        return messages, selection

    def _pin_operational_context(
        self,
        selection: ContextSelection,
        candidates: List[ContextCandidate],
        by_id: dict,
    ) -> ContextSelection:
        pinned = {"task_goal"}
        for candidate in reversed(candidates):
            if candidate.kind in {"assistant", "tool", "observation", "error"}:
                pinned.add(candidate.id)
            if len(pinned) >= 5:
                break

        keep: List[str] = []
        seen = set()
        for candidate in candidates:
            if candidate.id in pinned:
                keep.append(candidate.id)
                seen.add(candidate.id)

        used = sum(estimate_tokens(by_id[item].content) for item in keep if item in by_id)
        for item in selection.keep:
            if item in seen or item not in by_id:
                continue
            cost = estimate_tokens(by_id[item].content)
            if used + cost <= self.token_budget:
                keep.append(item)
                seen.add(item)
                used += cost

        drop = [candidate.id for candidate in candidates if candidate.id not in seen]
        reason = selection.reason or "Context selected."
        if any(item not in set(selection.keep) for item in pinned):
            reason = f"{reason} Recent tool observations were pinned to avoid repeated actions."
        return ContextSelection(keep=keep, drop=drop, update_memory=selection.update_memory, reason=reason)


CODING_SYSTEM_PROMPT = """You are a coding agent.

Return exactly one JSON object per response:
{
  "thought": "用简体中文简要说明当前判断",
  "action": "list_files|read_file|write_file|edit_file|run_command|run_tests|finish",
  "args": {}
}

Use local tools through JSON actions. Do not claim a file was changed until an
edit_file or write_file action has been executed. Prefer running tests after a
code change. After list_files, read the files most relevant to the task instead
of listing files again. If a tool fails or gives incomplete information, choose a
new action that gathers missing evidence. Use finish only when the task is
complete or blocked.

Write every thought and the finish summary in Simplified Chinese. Prioritize the
target implementation and its tests over unrelated files. Do not read an
unchanged file twice unless a tool result shows that more lines are needed. Once
you have enough evidence, edit the code promptly and reserve time to run tests."""


def load_weights(path: Path) -> RewardWeights:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RewardWeights(**payload)
