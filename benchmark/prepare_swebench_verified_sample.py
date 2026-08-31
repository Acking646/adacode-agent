from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a small SWE-Bench Verified sample for smoke tests.")
    parser.add_argument("--data", type=Path, default=Path("data/open/SWE-bench_Verified/test.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/open/SWE-bench_Verified/sample_instances.txt"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--repos", nargs="*", default=["sympy", "django", "pytest"])
    args = parser.parse_args()

    selected = []
    with args.data.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            instance_id = row.get("instance_id", "")
            repo = row.get("repo", "")
            if args.repos and not any(name.lower() in repo.lower() or name.lower() in instance_id.lower() for name in args.repos):
                continue
            selected.append(instance_id)
            if len(selected) >= args.limit:
                break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"Wrote {len(selected)} instances to {args.output}")
    for item in selected:
        print(item)


if __name__ == "__main__":
    main()

