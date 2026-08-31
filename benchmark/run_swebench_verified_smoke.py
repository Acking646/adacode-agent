from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def run(
    command: List[str],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        env=env,
        shell=False,
    )


def read_instances(data_path: Path, instance_ids: Optional[Iterable[str]], limit: int) -> List[Dict]:
    wanted = set(instance_ids or [])
    rows = []
    with data_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if wanted and row.get("instance_id") not in wanted:
                continue
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return rows


def load_instance_ids(path: Optional[Path]) -> Optional[List[str]]:
    if not path:
        return None
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def git_command(git_proxy: Optional[str], args: List[str]) -> List[str]:
    command = ["git"]
    command.extend(["-c", "http.version=HTTP/1.1", "-c", "http.lowSpeedLimit=0"])
    if git_proxy:
        command.extend(["-c", f"http.proxy={git_proxy}", "-c", f"https.proxy={git_proxy}"])
    command.extend(args)
    return command


def git_env() -> Dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_HTTP_LOW_SPEED_LIMIT", "0")
    env.setdefault("GIT_HTTP_LOW_SPEED_TIME", "999999")
    return env


def run_git_with_retry(
    git_proxy: Optional[str],
    args: List[str],
    cwd: Optional[Path],
    timeout: int,
    retries: int,
) -> subprocess.CompletedProcess:
    last = None
    for attempt in range(1, retries + 1):
        last = run(git_command(git_proxy, args), cwd=cwd, timeout=timeout, env=git_env())
        if last.returncode == 0:
            return last
        print(f"[WARN] git {' '.join(args[:2])} failed attempt {attempt}/{retries}:\n{last.stdout}", file=sys.stderr, flush=True)
    assert last is not None
    return last


def clone_instance(row: Dict, work_root: Path, git_proxy: Optional[str], git_retries: int, git_timeout: int) -> Path:
    repo = row["repo"]
    base_commit = row["base_commit"]
    instance_id = row["instance_id"]
    target = work_root / instance_id
    if target.exists():
        shutil.rmtree(str(target))
    url = f"https://github.com/{repo}.git"
    completed = run_git_with_retry(
        git_proxy,
        ["clone", "--no-tags", "--filter=blob:none", "--depth", "1", url, str(target)],
        cwd=None,
        timeout=git_timeout,
        retries=git_retries,
    )
    if completed.returncode != 0:
        if target.exists():
            shutil.rmtree(str(target))
        completed = run_git_with_retry(
            git_proxy,
            ["clone", "--no-tags", url, str(target)],
            cwd=None,
            timeout=max(git_timeout * 2, 1800),
            retries=git_retries,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"git clone failed for {repo}:\n{completed.stdout}")
    completed = run_git_with_retry(
        git_proxy,
        ["fetch", "--depth", "1", "origin", base_commit],
        cwd=target,
        timeout=git_timeout,
        retries=git_retries,
    )
    if completed.returncode != 0:
        completed = run_git_with_retry(
            git_proxy,
            ["fetch", "origin", base_commit],
            cwd=target,
            timeout=max(git_timeout * 2, 1800),
            retries=git_retries,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"git fetch failed for {instance_id}:\n{completed.stdout}")
    completed = run_git_with_retry(
        git_proxy,
        ["checkout", "--force", base_commit],
        cwd=target,
        timeout=git_timeout,
        retries=git_retries,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git checkout failed for {instance_id}:\n{completed.stdout}")
    return target


def run_agent(
    row: Dict,
    workspace: Path,
    model: str,
    max_steps: int,
    trace_root: Path,
    cm_mode: str,
    cm_model: str,
    cm_base_url: Optional[str],
    cm_api_key: str,
) -> str:
    task = (
        "Resolve this SWE-Bench issue. Edit the repository files locally and finish when a patch is ready.\n\n"
        f"Repository: {row.get('repo')}\n"
        f"Instance: {row.get('instance_id')}\n\n"
        f"Issue:\n{row.get('problem_statement', '')}\n"
    )
    trace_path = trace_root / f"{row['instance_id']}.jsonl"
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
        "--trace",
        str(trace_path),
        "--cm-mode",
        cm_mode,
    ]
    if cm_mode == "qwen":
        command.extend(["--cm-model", cm_model, "--cm-api-key", cm_api_key])
        if cm_base_url:
            command.extend(["--cm-base-url", cm_base_url])
    completed = run(command, cwd=Path.cwd(), timeout=1800)
    if completed.returncode != 0:
        print(f"[WARN] agent failed for {row['instance_id']}:\n{completed.stdout}", file=sys.stderr, flush=True)
    return completed.stdout


def git_diff(workspace: Path) -> str:
    completed = run(["git", "diff"], cwd=workspace, timeout=120)
    if completed.returncode != 0:
        return ""
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SWE-Bench Verified predictions with the base AdaCode-Agent.")
    parser.add_argument("--data", type=Path, default=Path("data/open/SWE-bench_Verified/test.jsonl"))
    parser.add_argument("--instances", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--work-root", type=Path, default=Path("outputs/swebench_workdirs"))
    parser.add_argument("--trace-root", type=Path, default=Path("outputs/swebench_traces"))
    parser.add_argument("--predictions", type=Path, default=Path("outputs/swebench_verified_predictions.jsonl"))
    parser.add_argument("--model", default=os.environ.get("ADACODE_MODEL", "deepseek-ai/DeepSeek-V4-Flash"))
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--cm-mode", choices=["rule", "qwen"], default="rule")
    parser.add_argument("--cm-model", default=os.environ.get("ADACODE_CM_MODEL", "qwen3-4b-cm"))
    parser.add_argument("--cm-base-url", default=os.environ.get("ADACODE_CM_BASE_URL"))
    parser.add_argument("--cm-api-key", default=os.environ.get("ADACODE_CM_API_KEY", "EMPTY"))
    parser.add_argument("--git-proxy", default=os.environ.get("GIT_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"))
    parser.add_argument("--git-retries", type=int, default=int(os.environ.get("GIT_RETRIES", "3")))
    parser.add_argument("--git-timeout", type=int, default=int(os.environ.get("GIT_TIMEOUT", "900")))
    args = parser.parse_args()

    ids = load_instance_ids(args.instances)
    rows = read_instances(args.data, ids, args.limit)
    if not rows:
        raise SystemExit("No SWE-Bench instances selected.")

    args.work_root.mkdir(parents=True, exist_ok=True)
    args.trace_root.mkdir(parents=True, exist_ok=True)
    args.predictions.parent.mkdir(parents=True, exist_ok=True)

    with args.predictions.open("w", encoding="utf-8") as fh:
        for index, row in enumerate(rows, start=1):
            instance_id = row["instance_id"]
            print(f"[{index}/{len(rows)}] {instance_id}", flush=True)
            try:
                workspace = clone_instance(row, args.work_root, args.git_proxy, args.git_retries, args.git_timeout)
                run_agent(
                    row,
                    workspace,
                    args.model,
                    args.max_steps,
                    args.trace_root,
                    args.cm_mode,
                    args.cm_model,
                    args.cm_base_url,
                    args.cm_api_key,
                )
                patch = git_diff(workspace)
            except Exception as exc:
                print(f"[WARN] failed {instance_id}: {exc}", file=sys.stderr, flush=True)
                patch = ""
            record = {
                "instance_id": instance_id,
                "model_name_or_path": f"adacode-agent-{args.cm_mode}-{args.model}",
                "model_patch": patch,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"patch_chars={len(patch)}", flush=True)
    print(f"Wrote predictions to {args.predictions}", flush=True)


if __name__ == "__main__":
    main()
