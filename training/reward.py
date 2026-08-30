from __future__ import annotations

import re


def context_reward(candidate_context: str, task: str, token_budget: int) -> float:
    """Reward used for context-selection filtering and analysis."""

    score = 0.0
    lower = candidate_context.lower()
    task_terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", task.lower()))
    score += sum(0.2 for term in task_terms if term in lower)

    if re.search(r"[\w./\\-]+\.(py|js|ts|java|cpp|c|go|rs)", candidate_context):
        score += 1.0
    if re.search(r"\b(test_[A-Za-z0-9_]+|FAILED|Traceback|AssertionError|Exception)\b", candidate_context):
        score += 2.0
    if re.search(r"\b(def|class|function|import|return)\b", candidate_context):
        score += 0.8
    if "obsolete" in lower or "outdated" in lower:
        score -= 1.5

    estimated_tokens = max(1, len(candidate_context) // 4)
    if estimated_tokens > token_budget:
        score -= (estimated_tokens - token_budget) / 500.0
    score -= estimated_tokens / 5000.0
    return score

