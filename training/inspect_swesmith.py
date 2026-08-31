from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_data_files(root: Path):
    patterns = ["*.parquet", "*.jsonl", "*.json"]
    files = []
    for pattern in patterns:
        files.extend(root.rglob(pattern))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect local SWE-smith trajectory files.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/open/SWE-smith-trajectories"))
    parser.add_argument("--split", default=None, help="Optional substring filter, e.g. xml/tool/ticks.")
    parser.add_argument("--rows", type=int, default=2)
    args = parser.parse_args()

    files = find_data_files(args.input_dir)
    if args.split:
        files = [path for path in files if args.split.lower() in str(path).lower()]
    if not files:
        raise SystemExit(f"No parquet/json files found under {args.input_dir}")

    print(f"Found {len(files)} files")
    for path in files[:20]:
        print(path)

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Install datasets first: pip install datasets pyarrow") from exc

    parquet_files = [str(path) for path in files if path.suffix == ".parquet"]
    json_files = [str(path) for path in files if path.suffix in {".jsonl", ".json"}]
    if parquet_files:
        dataset = load_dataset("parquet", data_files=parquet_files, split="train")
    else:
        dataset = load_dataset("json", data_files=json_files, split="train")

    print(f"Rows: {len(dataset)}")
    print("Columns:", dataset.column_names)
    for i, row in enumerate(dataset.select(range(min(args.rows, len(dataset))))):
        print(f"\n--- row {i} ---")
        preview = {}
        for key, value in row.items():
            text = json.dumps(value, ensure_ascii=False, default=str)
            preview[key] = text[:1200] + ("...[truncated]" if len(text) > 1200 else "")
        print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

