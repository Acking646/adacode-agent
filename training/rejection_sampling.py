from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.reward import context_reward


def filter_samples(input_path: Path, output_path: Path, min_reward: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    total = 0
    with input_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            total += 1
            sample = json.loads(line)
            task = json.dumps(sample.get("input", {}), ensure_ascii=False)
            context = json.dumps(sample.get("output", {}), ensure_ascii=False)
            reward = context_reward(context, task, sample.get("input", {}).get("token_budget", 3500))
            sample["reward"] = reward
            if reward >= min_reward:
                target.write(json.dumps(sample, ensure_ascii=False) + "\n")
                kept += 1
    print(f"Kept {kept}/{total} samples in {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-reward", type=float, default=0.0)
    args = parser.parse_args()
    filter_samples(args.input, args.output, args.min_reward)


if __name__ == "__main__":
    main()

