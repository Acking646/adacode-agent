from __future__ import annotations

import json
import re
from typing import Any, Dict

from .schema import Action


class ActionParseError(ValueError):
    """Raised when a model response cannot be parsed as an agent action."""


JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    match = JSON_BLOCK.search(text)
    if match:
        return json.loads(match.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ActionParseError("No JSON object found in model response.")


def parse_action(text: str) -> Action:
    try:
        payload = _extract_json_object(text)
    except json.JSONDecodeError as exc:
        raise ActionParseError(f"Invalid JSON action: {exc}") from exc

    action_name = payload.get("action") or payload.get("name")
    if not isinstance(action_name, str) or not action_name:
        raise ActionParseError("Action JSON must contain a non-empty action/name field.")

    args = payload.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ActionParseError("Action args must be a JSON object.")

    thought = payload.get("thought", "")
    if not isinstance(thought, str):
        thought = str(thought)

    return Action(name=action_name, args=args, thought=thought)
