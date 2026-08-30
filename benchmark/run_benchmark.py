from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List


def run_task(task_dir: Path, command: List[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / task_dir.name
        shutil.copytree(task_dir, work)
        task_file = work / "task.txt"
        task = task_file.read_text(encoding="utf-8") if task_file.exists() else "Fix the project."
        completed = subprocess.run(command + [task, "--workspace", str(work)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        test = subprocess.run(["python", "-m", "pytest", "-q"], cwd=str(work), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return {
            "task": task_dir.name,
            "agent_returncode": completed.returncode,
            "agent_output": completed.stdout[-4000:],
            "test_returncode": test.returncode,
            "test_output": test.stdout[-4000:],
            "passed": test.returncode == 0,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="benchmark/tasks", type=Path)
    parser.add_argument("--output", default="outputs/benchmark_results.jsonl", type=Path)
    parser.add_argument("--agent-command", nargs="+", default=["python", "-m", "agent.main"])
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    task_dirs = [p for p in args.tasks.iterdir() if p.is_dir()]
    passed = 0
    with args.output.open("w", encoding="utf-8") as fh:
        for task_dir in task_dirs:
            result = run_task(task_dir, args.agent_command)
            passed += int(result["passed"])
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(f"{task_dir.name}: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"Passed {passed}/{len(task_dirs)} tasks. Results: {args.output}")


if __name__ == "__main__":
    main()
