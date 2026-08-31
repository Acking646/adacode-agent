from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_PROGRAMS = [
    "bitcount",
    "breadth_first_search",
    "find_first_in_sorted",
    "flatten",
    "gcd",
    "get_factors",
    "is_valid_parenthesization",
    "kheapsort",
    "levenshtein",
    "lis",
]


def run(command: List[str], cwd: Optional[Path] = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        shell=False,
    )


def copy_worktree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(str(target))
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".mypy_cache", "*.pyc")
    shutil.copytree(str(source), str(target), ignore=ignore)
    run(["git", "init"], cwd=target)
    run(["git", "add", "."], cwd=target)
    run(["git", "-c", "user.email=adacode@example.invalid", "-c", "user.name=AdaCode", "commit", "-m", "baseline"], cwd=target)


def discover_programs(repo_root: Path, limit: int) -> List[str]:
    program_dir = repo_root / "python_programs"
    if not program_dir.is_dir():
        raise FileNotFoundError(f"Missing QuixBugs python_programs directory: {program_dir}")
    programs = [path.stem for path in sorted(program_dir.glob("*.py")) if not path.name.startswith("__")]
    return programs[:limit] if limit else programs


def test_command(program: str) -> List[str]:
    return [sys.executable, "-m", "pytest", "-q", f"python_testcases/test_{program}.py"]


def run_tests(workspace: Path, program: str, timeout: int) -> subprocess.CompletedProcess:
    return run(test_command(program), cwd=workspace, timeout=timeout)


def run_agent(
    workspace: Path,
    program: str,
    model: str,
    max_steps: int,
    trace_path: Path,
    cm_mode: str,
    cm_model: str,
    cm_base_url: Optional[str],
    cm_api_key: str,
    llm_timeout: int,
    llm_retries: int,
) -> subprocess.CompletedProcess:
    task = (
        f"Fix the buggy QuixBugs Python implementation `{program}`.\n"
        f"Primary source file: python_programs/{program}.py\n"
        f"Validation command: python -m pytest -q python_testcases/test_{program}.py\n"
        "Edit the implementation so the test passes. Prefer a minimal patch."
    )
    command = [
        sys.executable,
        "-m",
        "agent.main",
        task,
        "--workspace",
        str(workspace),
        "--model",
        model,
        "--max-steps",
        str(max_steps),
        "--llm-timeout",
        str(llm_timeout),
        "--llm-retries",
        str(llm_retries),
        "--trace",
        str(trace_path),
        "--cm-mode",
        cm_mode,
    ]
    if cm_mode == "qwen":
        command.extend(["--cm-model", cm_model, "--cm-api-key", cm_api_key])
        if cm_base_url:
            command.extend(["--cm-base-url", cm_base_url])
    return run(command, cwd=Path.cwd(), timeout=max(llm_timeout * max_steps * max(1, llm_retries), 1800))


def git_diff(workspace: Path) -> str:
    completed = run(["git", "diff"], cwd=workspace, timeout=120)
    return completed.stdout if completed.returncode == 0 else ""


def trim(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated {len(text) - max_chars} chars]"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AdaCode-Agent on the QuixBugs Python benchmark.")
    parser.add_argument("--repo-root", type=Path, default=Path("data/open/QuixBugs"))
    parser.add_argument("--programs", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--work-root", type=Path, default=Path("outputs/quixbugs_workdirs"))
    parser.add_argument("--trace-root", type=Path, default=Path("outputs/quixbugs_traces"))
    parser.add_argument("--output", type=Path, default=Path("outputs/quixbugs_results.jsonl"))
    parser.add_argument("--model", default=os.environ.get("ADACODE_MODEL", "deepseek-ai/DeepSeek-V4-Flash"))
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--test-timeout", type=int, default=120)
    parser.add_argument("--llm-timeout", type=int, default=int(os.environ.get("ADACODE_LLM_TIMEOUT", "300")))
    parser.add_argument("--llm-retries", type=int, default=int(os.environ.get("ADACODE_LLM_RETRIES", "5")))
    parser.add_argument("--cm-mode", choices=["rule", "qwen"], default="rule")
    parser.add_argument("--cm-model", default=os.environ.get("ADACODE_CM_MODEL", "qwen3-4b-cm"))
    parser.add_argument("--cm-base-url", default=os.environ.get("ADACODE_CM_BASE_URL"))
    parser.add_argument("--cm-api-key", default=os.environ.get("ADACODE_CM_API_KEY", "EMPTY"))
    args = parser.parse_args()

    if not args.repo_root.is_dir():
        raise SystemExit(f"QuixBugs not found: {args.repo_root}. Run scripts/download_quixbugs_resumable.sh first.")

    programs = args.programs or discover_programs(args.repo_root, args.limit)
    if args.limit and args.programs:
        programs = programs[: args.limit]

    args.work_root.mkdir(parents=True, exist_ok=True)
    args.trace_root.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    passed = 0
    with args.output.open("w", encoding="utf-8") as fh:
        for index, program in enumerate(programs, start=1):
            started = time.time()
            print(f"[{index}/{len(programs)}] {program}", flush=True)
            workspace = args.work_root / program
            record: Dict[str, object] = {
                "benchmark": "QuixBugs-Python",
                "program": program,
                "model": args.model,
                "cm_mode": args.cm_mode,
            }
            try:
                copy_worktree(args.repo_root, workspace)
                source = workspace / "python_programs" / f"{program}.py"
                test = workspace / "python_testcases" / f"test_{program}.py"
                if not source.is_file() or not test.is_file():
                    raise FileNotFoundError(f"Missing source/test for {program}")

                before = run_tests(workspace, program, args.test_timeout)
                trace_path = args.trace_root / f"{program}.jsonl"
                agent = run_agent(
                    workspace,
                    program,
                    args.model,
                    args.max_steps,
                    trace_path,
                    args.cm_mode,
                    args.cm_model,
                    args.cm_base_url,
                    args.cm_api_key,
                    args.llm_timeout,
                    args.llm_retries,
                )
                after = run_tests(workspace, program, args.test_timeout)
                patch = git_diff(workspace)
                ok = after.returncode == 0
                passed += int(ok)
                record.update(
                    {
                        "before_passed": before.returncode == 0,
                        "passed": ok,
                        "patch_chars": len(patch),
                        "model_patch": patch,
                        "agent_returncode": agent.returncode,
                        "before_output": trim(before.stdout),
                        "after_output": trim(after.stdout),
                        "agent_output": trim(agent.stdout),
                    }
                )
                print(f"passed={ok} patch_chars={len(patch)}", flush=True)
            except Exception as exc:
                record.update({"passed": False, "patch_chars": 0, "error": f"{type(exc).__name__}: {exc}"})
                print(f"[WARN] failed {program}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            record["elapsed_seconds"] = round(time.time() - started, 2)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
    print(f"passed={passed}/{len(programs)} output={args.output}", flush=True)


if __name__ == "__main__":
    main()
