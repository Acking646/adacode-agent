from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from .context_manager import ContextManager
from .llm_client import LLMClient
from .memory import MemoryStore, extract_failure_memories
from .parser import ActionParseError, parse_action
from .schema import Message
from .tools import ToolExecutor


@dataclass
class AgentConfig:
    workspace: Path
    max_steps: int = 20
    memory_path: Optional[Path] = None
    trace_path: Optional[Path] = None
    token_budget: int = 3500


class CodingAgent:
    def __init__(self, llm: LLMClient, config: AgentConfig, context_manager: Optional[ContextManager] = None) -> None:
        self.llm = llm
        self.config = config
        self.workspace = config.workspace.resolve()
        self.memory = MemoryStore(config.memory_path or self.workspace / ".adacode" / "memory.json")
        self.context_manager = context_manager or ContextManager(self.memory, token_budget=config.token_budget)
        self.tools = ToolExecutor(self.workspace)
        self.history: List[Message] = []
        self.step_index = 0

    def run(self, task: str) -> str:
        self.history.append(Message(self._id("task"), "user", task, "task"))
        final_summary = ""
        for _ in range(self.config.max_steps):
            self.step_index += 1
            managed_messages, selection = self.context_manager.assemble(task, self.history)
            model_text = self.llm.complete(managed_messages)
            self.history.append(Message(self._id("assistant"), "assistant", model_text, "assistant"))

            try:
                action = parse_action(model_text)
            except ActionParseError as exc:
                observation = f"Action parse error: {exc}. Return a valid JSON action."
                self.history.append(Message(self._id("parse_error"), "tool", observation, "error"))
                self._trace({"event": "parse_error", "error": str(exc), "model_text": model_text})
                continue

            result = self.tools.dispatch(action.name, action.args)
            observation = result.output
            self.history.append(
                Message(
                    self._id("tool"),
                    "tool",
                    observation,
                    "observation",
                    {"tool": action.name, "ok": result.ok, **result.metadata},
                )
            )

            if action.name in {"run_tests", "run_command"} and not result.ok:
                for item in extract_failure_memories(result.output):
                    self.memory.add(**item)

            self._trace(
                {
                    "event": "step",
                    "step": self.step_index,
                    "selection": asdict(selection),
                    "action": asdict(action),
                    "result": {"ok": result.ok, "metadata": result.metadata, "output": result.output[:4000]},
                }
            )

            if result.metadata.get("finished"):
                final_summary = result.output
                break

        if not final_summary:
            final_summary = "Stopped after reaching max_steps."
        return final_summary

    def _id(self, prefix: str) -> str:
        return f"{prefix}_{self.step_index:04d}_{len(self.history) + 1:04d}"

    def _trace(self, payload: dict) -> None:
        if not self.config.trace_path:
            return
        self.config.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
