from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
from typing import Dict, List, Optional, Set, Tuple

from agent.context_manager import RuleBasedSelectionModel, TrainedJSONSelectionModel, estimate_tokens
from agent.llm_client import OpenAICompatibleClient
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


def select_ids(
    mode: str,
    sample: Dict,
    candidates: List[ContextCandidate],
    token_budget: int,
    qwen_selector: Optional[TrainedJSONSelectionModel] = None,
) -> Tuple[Set[str], bool]:
    if mode == "full":
        return {candidate.id for candidate in candidates}, True
    if mode == "sliding":
        keep = {"task_goal"}
        used = 0
        for candidate in reversed(candidates):
            cost = estimate_tokens(candidate.content)
            if used + cost <= token_budget:
                keep.add(candidate.id)
                used += cost
        return keep, True
    if mode == "rule":
        selector = RuleBasedSelectionModel()
        task = sample.get("input", {}).get("task", "")
        return set(selector.select(task, candidates, token_budget).keep), True
    if mode == "qwen":
        if qwen_selector is None:
            raise ValueError("qwen mode requires --qwen-base-url and --qwen-model.")
        task = sample.get("input", {}).get("task", "")
        try:
            selection = qwen_selector.select(task, candidates, token_budget)
            valid_ids = {candidate.id for candidate in candidates}
            return {item for item in selection.keep if item in valid_ids}, True
        except Exception as exc:
            print(f"[WARN] qwen selection failed: {type(exc).__name__}: {exc}")
            return set(), False
    raise ValueError(f"Unknown mode: {mode}")


def evaluate(
    path: Path,
    modes: List[str],
    token_budget: int,
    qwen_base_url: Optional[str],
    qwen_model: str,
    qwen_api_key: str,
) -> None:
    samples = load_samples(path)
    print(f"samples={len(samples)} token_budget={token_budget}")
    qwen_selector = None
    if "qwen" in modes:
        client = OpenAICompatibleClient(
            model=qwen_model,
            base_url=qwen_base_url,
            api_key=qwen_api_key,
        )
        qwen_selector = TrainedJSONSelectionModel(client)
    for mode in modes:
        tp = fp = fn = 0
        predicted_tokens = full_tokens = 0
        valid = 0
        for sample in samples:
            candidates = as_candidates(sample)
            gold = set(str(item) for item in sample.get("output", {}).get("keep", []))
            pred, ok = select_ids(mode, sample, candidates, token_budget, qwen_selector)
            valid += int(ok)
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
    parser.add_argument("--qwen-base-url", default=os.environ.get("ADACODE_CM_BASE_URL"))
    parser.add_argument("--qwen-model", default=os.environ.get("ADACODE_CM_MODEL", "qwen3-4b-cm"))
    parser.add_argument("--qwen-api-key", default=os.environ.get("ADACODE_CM_API_KEY", "EMPTY"))
    args = parser.parse_args()
    evaluate(args.data, args.modes, args.token_budget, args.qwen_base_url, args.qwen_model, args.qwen_api_key)


if __name__ == "__main__":
    main()
