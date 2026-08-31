from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize AdaCode-Agent JSONL benchmark results.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    rows = []
    with args.path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))

    total = len(rows)
    if not total:
        print("total=0")
        return

    nonempty = sum(bool(str(row.get("model_patch", "")).strip()) for row in rows)
    pass_values = [row.get("passed") for row in rows if "passed" in row]
    valid_pass = [value for value in pass_values if isinstance(value, bool)]

    print(f"file={args.path}")
    print(f"total={total}")
    print(f"nonempty_patch={nonempty}")
    print(f"empty_patch={total - nonempty}")
    if valid_pass:
        passed = sum(valid_pass)
        print(f"passed={passed}")
        print(f"pass_rate={passed / len(valid_pass):.4f}")

    for row in rows:
        name = row.get("instance_id") or row.get("program") or row.get("task_id") or "unknown"
        patch = str(row.get("model_patch", ""))
        status = ""
        if "passed" in row:
            status = f" passed={row.get('passed')}"
        print(f"{name} patch_chars={len(patch)}{status}")


if __name__ == "__main__":
    main()
