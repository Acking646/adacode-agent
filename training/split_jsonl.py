from __future__ import annotations

import argparse
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a JSONL file into train/dev/test files.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prefix", default="context_manager")
    args = parser.parse_args()

    lines = [line for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(args.seed)
    rng.shuffle(lines)

    train_end = int(len(lines) * args.train_ratio)
    dev_end = train_end + int(len(lines) * args.dev_ratio)
    splits = {
        "train": lines[:train_end],
        "dev": lines[train_end:dev_end],
        "test": lines[dev_end:],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        path = args.output_dir / f"{args.prefix}_{name}.jsonl"
        path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        print(f"{name}: {len(rows)} -> {path}")


if __name__ == "__main__":
    main()
