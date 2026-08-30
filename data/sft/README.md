# Context Manager SFT Data

The SFT data trains the context manager to select compact context for the next
coding-agent step.

Each JSONL row has this schema:

```json
{
  "instruction": "Select useful context for the next coding-agent step under the token budget. Return only JSON.",
  "input": {
    "task": "Fix the divide function so all tests pass.",
    "last_error": "FAILED test_calculator.py::test_divide_by_zero_returns_none",
    "candidates": [
      {
        "id": "task_goal",
        "type": "task",
        "content": "Fix divide; return None when divisor is zero."
      },
      {
        "id": "error_0002",
        "type": "pytest_error",
        "content": "ZeroDivisionError in calculator.py::divide"
      }
    ],
    "token_budget": 3500
  },
  "output": {
    "keep": ["task_goal", "error_0002"],
    "drop": [],
    "update_memory": [],
    "reason": "Keep the task goal and the current failing test."
  }
}
```

Recommended data sources:

1. Run AdaCode-Agent on `MiniCodeBench-CM` tasks and save trajectories.
2. Convert trajectories with `training.build_sft_dataset`.
3. Manually review or LLM-review `keep/drop/update_memory` labels.
4. Optionally apply reward-guided rejection sampling.

Do not train primarily on SWE-Bench first. Use SWE-Bench Lite or Verified only as
a small smoke test after the mini benchmark pipeline is stable.

