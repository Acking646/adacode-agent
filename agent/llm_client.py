from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from .schema import Message


class LLMClient:
    def complete(self, messages: List[Message]) -> str:
        """Return the assistant response text."""


@dataclass
class OpenAICompatibleClient:
    """Minimal OpenAI-compatible chat completions client.

    This is intentionally small: it only calls the language model endpoint. Tool
    execution, parsing, retries, and loop control are implemented locally.
    """

    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    timeout: int = 60

    def __post_init__(self) -> None:
        self.api_key = (
            self.api_key
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("SILICONFLOW_API_KEY")
        )
        self.base_url = (self.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    def complete(self, messages: List[Message]) -> str:
        if not self.api_key:
            raise RuntimeError("Missing API key. Set OPENAI_API_KEY, LLM_API_KEY, or SILICONFLOW_API_KEY.")

        body = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error {exc.code}: {details}") from exc

        return payload["choices"][0]["message"]["content"]


class ScriptedClient:
    """Deterministic client used by tests and demos without external APIs."""

    def __init__(self, responses: List[str]) -> None:
        self.responses = list(responses)
        self.calls: List[List[Message]] = []

    def complete(self, messages: List[Message]) -> str:
        self.calls.append(messages)
        if not self.responses:
            return '{"action": "finish", "args": {"summary": "No scripted response left."}}'
        return self.responses.pop(0)
