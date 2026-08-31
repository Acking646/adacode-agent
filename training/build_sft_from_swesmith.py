from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


KEYWORDS = [
    "error",
    "failed",
    "failure",
    "traceback",
    "exception",
    "assert",
    "pytest",
    "test_",
    ".py",
    "diff",
    "patch",
]


def find_data_files(root: Path, split: str) -> List[Path]:
    files = sorted(list(root.rglob("*.parquet")) + list(root.rglob("*.jsonl")) + list(root.rglob("*.json")))
    if split:
        filtered = [path for path in files if split.lower() in str(path).lower()]
        if filtered:
            return filtered
    return files


def first_text(row: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        if key in row and row[key]:
            return stringify(row[key])[:4000]
    return default


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def split_chunks(text: str, max_chars: int) -> List[str]:
    text = text.strip()
    if not text:
        return []
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def extract_trajectory_text(row: Dict[str, Any]) -> str:
    keys = [
        "trajectory",
        "traj",
        "messages",
        "history",
        "conversation",
        "steps",
        "interactions",
        "transcript",
        "output",
    ]
    text = first_text(row, keys)
    if text:
        return text
    return stringify(row)


def infer_task(row: Dict[str, Any]) -> str:
    task = first_text(
        row,
        [
            "problem_statement",
            "issue",
            "task",
            "instruction",
            "prompt",
            "query",
            "repo",
            "instance_id",
        ],
        default="Select useful context for a software-engineering trajectory.",
    )
    return task[:2000]


def make_candidates(row: Dict[str, Any], max_candidates: int, chunk_chars: int) -> List[Dict[str, str]]:
    task = infer_task(row)
    candidates = [{"id": "task_goal", "type": "task", "content": task}]

    trajectory = extract_trajectory_text(row)
    chunks = split_chunks(trajectory, chunk_chars)
    for idx, chunk in enumerate(chunks[: max_candidates - 1], start=1):
        lower = chunk.lower()
        if any(word in lower for word in ["traceback", "failed", "error", "exception", "pytest", "assert"]):
            kind = "error_or_test"
        elif any(word in lower for word in ["diff", "patch", "@@", "```"]):
            kind = "code_or_patch"
        elif any(word in lower for word in ["tool", "observation", "command", "stdout", "stderr"]):
            kind = "tool_observation"
        else:
            kind = "history"
        candidates.append({"id": f"traj_{idx:04d}", "type": kind, "content": chunk})
    return candidates


def heuristic_keep(candidates: List[Dict[str, str]], token_budget: int) -> List[str]:
    keep = ["task_goal"]
    scored = []
    for idx, candidate in enumerate(candidates):
        if candidate["id"] == "task_goal":
            continue
        lower = candidate["content"].lower()
        score = 0
        score += sum(2 for word in KEYWORDS if word in lower)
        score += 2 if candidate["type"] in {"error_or_test", "code_or_patch"} else 0
        score += 1 if idx > max(0, len(candidates) - 6) else 0
        score -= len(candidate["content"]) / 3000.0
        scored.append((score, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)

    used = sum(max(1, len(c["content"]) // 4) for c in candidates if c["id"] in keep)
    for _, candidate in scored:
        cost = max(1, len(candidate["content"]) // 4)
        if used + cost <= token_budget:
            keep.append(candidate["id"])
            used += cost
    return keep


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def convert(
    input_dir: Path,
    output: Path,
    split: str,
    max_samples: int,
    max_candidates: int,
    chunk_chars: int,
    token_budget: int,
    min_full_tokens: int,
) -> None:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Install datasets first: pip install datasets pyarrow") from exc

    files = find_data_files(input_dir, split)
    if not files:
        raise SystemExit(f"No data files found under {input_dir}")

    parquet_files = [str(path) for path in files if path.suffix == ".parquet"]
    json_files = [str(path) for path in files if path.suffix in {".jsonl", ".json"}]
    if parquet_files:
        dataset = load_dataset("parquet", data_files=parquet_files, split="train")
    else:
        dataset = load_dataset("json", data_files=json_files, split="train")

    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped_short = 0
    scanned = 0
    with output.open("w", encoding="utf-8") as fh:
        for row in dataset:
            scanned += 1
            candidates = make_candidates(row, max_candidates=max_candidates, chunk_chars=chunk_chars)
            if len(candidates) < 2:
                continue
            full_tokens = sum(estimate_tokens(candidate["content"]) for candidate in candidates)
            if min_full_tokens and full_tokens < min_full_tokens:
                skipped_short += 1
                continue
            keep = heuristic_keep(candidates, token_budget)
            drop = [candidate["id"] for candidate in candidates if candidate["id"] not in keep]
            sample = {
                "instruction": "Select useful context for the next coding-agent step under the token budget. Return only JSON.",
                "input": {
                    "task": infer_task(row),
                    "last_error": infer_last_error(candidates),
                    "candidates": candidates,
                    "token_budget": token_budget,
                },
                "output": {
                    "keep": keep,
                    "drop": drop,
                    "update_memory": [],
                    "reason": "Keep task, recent failures, code patches, and relevant tool observations under the token budget.",
                },
            }
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break
    print(f"Scanned {scanned} rows; skipped_short={skipped_short}; wrote {count} samples to {output}")


def infer_last_error(candidates: List[Dict[str, str]]) -> str:
    for candidate in candidates:
        if candidate["type"] == "error_or_test":
            lines = candidate["content"].splitlines()
            selected = [line for line in lines if re.search(r"failed|error|traceback|exception|assert|test_", line, re.I)]
            return "\n".join(selected[:12])[:1600] or candidate["content"][:1600]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build context-manager SFT data from local SWE-smith trajectories.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/open/SWE-smith-trajectories"))
    parser.add_argument("--output", type=Path, default=Path("data/sft/context_manager_sft.jsonl"))
    parser.add_argument("--split", default="xml", help="Prefer files whose path contains this split name.")
    parser.add_argument("--max-samples", type=int, default=500)
    parser.add_argument("--max-candidates", type=int, default=24)
    parser.add_argument("--chunk-chars", type=int, default=1800)
    parser.add_argument("--token-budget", type=int, default=3500)
    parser.add_argument("--min-full-tokens", type=int, default=0)
    args = parser.parse_args()
    convert(
        args.input_dir,
        args.output,
        args.split,
        args.max_samples,
        args.max_candidates,
        args.chunk_chars,
        args.token_budget,
        args.min_full_tokens,
    )


if __name__ == "__main__":
    main()
