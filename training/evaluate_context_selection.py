from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

from agent.context_manager import RuleBasedSelectionModel, estimate_tokens
from agent.schema import ContextCandidate


def load_samples(path: Path) -> List[Dict]:
    samples = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def as_candidates(sample: Dict) -> List[ContextCandidate]:
    candidates = []
    for item in sample.get("input", {}).get("candidates", []):
        candidates.append(
            ContextCandidate(
                id=str(item.get("id")),
                kind=str(item.get("type", "history")),
                content=str(item.get("content", "")),
                metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
            )
        )
    return candidates


def select_ids(mode: str, sample: Dict, candidates: List[ContextCandidate], token_budget: int) -> Set[str]:
    if mode == "full":
        return {candidate.id for candidate in candidates}
    if mode == "sliding":
        keep = {"task_goal"}
        used = 0
        for candidate in reversed(candidates):
            cost = estimate_tokens(candidate.content)
            if used + cost <= token_budget:
                keep.add(candidate.id)
                used += cost
        return keep
    if mode == "rule":
        selector = RuleBasedSelectionModel()
        task = sample.get("input", {}).get("task", "")
        return set(selector.select(task, candidates, token_budget).keep)
    raise ValueError(f"Unknown mode: {mode}")


def evaluate(path: Path, modes: List[str], token_budget: int) -> None:
    samples = load_samples(path)
    print(f"samples={len(samples)} token_budget={token_budget}")
    for mode in modes:
        tp = fp = fn = 0
        predicted_tokens = full_tokens = 0
        valid = 0
        for sample in samples:
            candidates = as_candidates(sample)
            gold = set(str(item) for item in sample.get("output", {}).get("keep", []))
            pred = select_ids(mode, sample, candidates, token_budget)
            valid += 1
            tp += len(pred & gold)
            fp += len(pred - gold)
            fn += len(gold - pred)
            by_id = {candidate.id: candidate for candidate in candidates}
            predicted_tokens += sum(estimate_tokens(by_id[item].content) for item in pred if item in by_id)
            full_tokens += sum(estimate_tokens(candidate.content) for candidate in candidates)
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-9, precision + recall)
        compression = 1.0 - predicted_tokens / max(1, full_tokens)
        print(
            json.dumps(
                {
                    "mode": mode,
                    "json_valid": valid / max(1, len(samples)),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "f1": round(f1, 4),
                    "avg_selected_tokens": round(predicted_tokens / max(1, len(samples)), 2),
                    "compression": round(compression, 4),
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate context selection without training.")
    parser.add_argument("--data", type=Path, default=Path("data/sft/context_manager_sft.jsonl"))
    parser.add_argument("--modes", nargs="+", default=["full", "sliding", "rule"])
    parser.add_argument("--token-budget", type=int, default=3500)
    args = parser.parse_args()
    evaluate(args.data, args.modes, args.token_budget)


if __name__ == "__main__":
    main()

