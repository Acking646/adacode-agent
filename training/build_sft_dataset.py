from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert_trace(trace_path: Path, output_path: Path) -> None:
    """Convert agent trajectories into JSONL SFT samples.

    The conversion is intentionally conservative. It uses the context selected by
    the rule manager as a bootstrapping label, which can later be refined by
    manual review or reward-guided rejection sampling.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with trace_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            event = json.loads(line)
            if event.get("event") != "step":
                continue
            selection = event.get("selection", {})
            action = event.get("action", {})
            result = event.get("result", {})
            sample = {
                "instruction": "Select useful context for the next coding-agent step under the token budget. Return only JSON.",
                "input": {
                    "previous_action": action,
                    "last_result": {
                        "ok": result.get("ok"),
                        "metadata": result.get("metadata", {}),
                        "output": result.get("output", "")[:1600],
                    },
                    "token_budget": 3500,
                },
                "output": {
                    "keep": selection.get("keep", []),
                    "drop": selection.get("drop", []),
                    "update_memory": selection.get("update_memory", []),
                    "reason": selection.get("reason", "Selected by bootstrapped rule manager."),
                },
            }
            target.write(json.dumps(sample, ensure_ascii=False) + "\n")
            count += 1
    print(f"Wrote {count} SFT samples to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--output", default=Path("data/sft/context_manager_sft.jsonl"), type=Path)
    args = parser.parse_args()
    convert_trace(args.trace, args.output)


if __name__ == "__main__":
    main()

