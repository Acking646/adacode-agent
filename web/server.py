from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from agent.context_manager import ContextManager, TrainedJSONSelectionModel
from agent.controller import AgentConfig, CodingAgent
from agent.llm_client import OpenAICompatibleClient
from agent.memory import MemoryStore


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web" / "static"
INDEX = ROOT / "web" / "templates" / "index.html"
OUTPUTS = ROOT / "outputs"
DEMO_SOURCE = ROOT / "examples" / "demo_project"
DEMO_WORKSPACE = OUTPUTS / "web_demo_workspace"

JOBS: Dict[str, Dict[str, Any]] = {}
LOCK = threading.Lock()


def run(command: List[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        shell=False,
    )


def trim(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def resolve_workspace(raw: str) -> Path:
    path = Path(raw or ".")
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    root = ROOT.resolve()
    if path != root and root not in path.parents:
        raise ValueError("Workspace must stay inside the project directory.")
    return path


def ensure_git_baseline(workspace: Path) -> None:
    if (workspace / ".git").is_dir():
        return
    run(["git", "init"], cwd=workspace)
    run(["git", "add", "."], cwd=workspace)
    run(
        ["git", "-c", "user.email=adacode@example.invalid", "-c", "user.name=AdaCode", "commit", "-m", "baseline"],
        cwd=workspace,
    )


def reset_demo_workspace() -> Dict[str, Any]:
    if DEMO_WORKSPACE.exists():
        shutil.rmtree(str(DEMO_WORKSPACE), onerror=make_writable_and_retry)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        str(DEMO_SOURCE),
        str(DEMO_WORKSPACE),
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    ensure_git_baseline(DEMO_WORKSPACE)
    task = (DEMO_WORKSPACE / "task.txt").read_text(encoding="utf-8").strip()
    return {
        "workspace": str(DEMO_WORKSPACE.relative_to(ROOT)).replace("\\", "/"),
        "task": task,
        "files": list_files(DEMO_WORKSPACE),
    }


def list_files(workspace: Path, max_files: int = 120) -> List[str]:
    ignored = {".git", "__pycache__", ".pytest_cache", ".adacode"}
    files: List[str] = []
    for current, dirs, names in os.walk(workspace):
        dirs[:] = [item for item in dirs if item not in ignored]
        for name in sorted(names):
            rel = Path(current, name).resolve().relative_to(workspace)
            files.append(str(rel).replace("\\", "/"))
            if len(files) >= max_files:
                return files
    return files


def make_writable_and_retry(function, path: str, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def parse_trace(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"event": "trace_parse_error", "raw": line[:1000]})
    return rows


def summarize_trace(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    actions = []
    selected = 0
    dropped = 0
    for row in rows:
        if row.get("event") != "step":
            continue
        action = row.get("action", {})
        result = row.get("result", {})
        selection = row.get("selection", {})
        selected += len(selection.get("keep", []) or [])
        dropped += len(selection.get("drop", []) or [])
        actions.append(
            {
                "step": row.get("step"),
                "name": action.get("name"),
                "args": action.get("args", {}),
                "ok": result.get("ok"),
                "output": trim(str(result.get("output", "")), 2400),
                "keep": selection.get("keep", []),
                "drop": selection.get("drop", []),
                "reason": selection.get("reason", ""),
            }
        )
    return {"steps": len(actions), "selected": selected, "dropped": dropped, "actions": actions}


def git_diff(workspace: Path) -> str:
    completed = run(["git", "diff"], cwd=workspace)
    if completed.returncode != 0:
        return ""
    return completed.stdout


def run_tests(workspace: Path, command: List[str]) -> Dict[str, Any]:
    try:
        if command and command[0] in {"python", "python3"}:
            command = [sys.executable, *command[1:]]
        completed = run(command, cwd=workspace, timeout=180)
        return {"ok": completed.returncode == 0, "returncode": completed.returncode, "output": trim(completed.stdout)}
    except Exception as exc:
        return {"ok": False, "returncode": -1, "output": f"{type(exc).__name__}: {exc}"}


def set_job(job_id: str, **updates: Any) -> None:
    with LOCK:
        JOBS[job_id].update(updates)


def worker(job_id: str, payload: Dict[str, Any]) -> None:
    started = time.time()
    workspace = resolve_workspace(str(payload.get("workspace") or DEMO_WORKSPACE))
    trace_path = OUTPUTS / "web_traces" / f"{job_id}.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if trace_path.exists():
        trace_path.unlink()

    try:
        set_job(job_id, status="running", message="Preparing workspace")
        ensure_git_baseline(workspace)
        test_command = payload.get("test_command") or [sys.executable, "-m", "pytest", "-q"]
        before = run_tests(workspace, test_command)

        model = str(payload.get("model") or os.getenv("ADACODE_MODEL") or "deepseek-ai/DeepSeek-V4-Flash")
        base_url = payload.get("base_url") or os.getenv("OPENAI_BASE_URL")
        llm = OpenAICompatibleClient(
            model=model,
            base_url=base_url,
            timeout=int(payload.get("llm_timeout") or 300),
            retries=int(payload.get("llm_retries") or 5),
            max_tokens=int(payload.get("max_tokens") or 2048),
        )

        memory = MemoryStore(workspace / ".adacode" / "memory.json")
        context_manager = None
        if payload.get("cm_mode") == "qwen":
            cm_llm = OpenAICompatibleClient(
                model=str(payload.get("cm_model") or "cm"),
                api_key=str(payload.get("cm_api_key") or "EMPTY"),
                base_url=str(payload.get("cm_base_url") or "http://127.0.0.1:8001/v1"),
                timeout=300,
                retries=2,
                max_tokens=1024,
            )
            context_manager = ContextManager(
                memory,
                selector=TrainedJSONSelectionModel(cm_llm),
                token_budget=int(payload.get("token_budget") or 1200),
            )

        set_job(job_id, message="Running agent")
        agent = CodingAgent(
            llm,
            AgentConfig(
                workspace=workspace,
                max_steps=int(payload.get("max_steps") or 8),
                trace_path=trace_path,
                token_budget=int(payload.get("token_budget") or 1200),
            ),
            context_manager=context_manager,
        )
        summary = agent.run(str(payload.get("task") or "Fix the project so tests pass."))
        after = run_tests(workspace, test_command)
        patch = git_diff(workspace)
        rows = parse_trace(trace_path)
        trace_summary = summarize_trace(rows)
        set_job(
            job_id,
            status="done",
            message="Completed",
            summary=summary,
            before=before,
            after=after,
            patch=patch,
            patch_chars=len(patch),
            trace=trace_summary,
            files=list_files(workspace),
            elapsed_seconds=round(time.time() - started, 2),
        )
    except Exception as exc:
        rows = parse_trace(trace_path)
        set_job(
            job_id,
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            trace=summarize_trace(rows),
            elapsed_seconds=round(time.time() - started, 2),
        )


class Handler(BaseHTTPRequestHandler):
    server_version = "AdaCodeWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_file(INDEX, "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            name = parsed.path.removeprefix("/static/")
            path = (STATIC / name).resolve()
            if STATIC.resolve() not in path.parents:
                self.send_json({"error": "invalid static path"}, HTTPStatus.BAD_REQUEST)
                return
            content_type = "text/plain"
            if path.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif path.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            self.send_file(path, content_type)
            return
        if parsed.path == "/api/job":
            query = parse_qs(parsed.query)
            job_id = (query.get("id") or [""])[0]
            with LOCK:
                job = JOBS.get(job_id)
            if not job:
                self.send_json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
                return
            if job.get("status") == "running":
                trace_path = Path(str(job.get("trace_path")))
                job = dict(job)
                job["trace"] = summarize_trace(parse_trace(trace_path))
            self.send_json(job)
            return
        if parsed.path == "/api/file":
            query = parse_qs(parsed.query)
            workspace = resolve_workspace((query.get("workspace") or [""])[0])
            rel = (query.get("path") or [""])[0]
            path = (workspace / rel).resolve()
            if workspace not in path.parents and path != workspace:
                self.send_json({"error": "path escapes workspace"}, HTTPStatus.BAD_REQUEST)
                return
            if not path.is_file():
                self.send_json({"error": "file not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"path": rel, "content": path.read_text(encoding="utf-8", errors="replace")})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/demo/reset":
                self.send_json(reset_demo_workspace())
                return
            if parsed.path == "/api/run":
                job_id = uuid.uuid4().hex[:12]
                trace_path = OUTPUTS / "web_traces" / f"{job_id}.jsonl"
                with LOCK:
                    JOBS[job_id] = {
                        "id": job_id,
                        "status": "queued",
                        "message": "Queued",
                        "trace_path": str(trace_path),
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                thread = threading.Thread(target=worker, args=(job_id, payload), daemon=True)
                thread.start()
                self.send_json({"job_id": job_id})
                return
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.BAD_REQUEST)

    def read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_json({"error": "file not found"}, HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AdaCode-Agent web console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AdaCode-Agent web console: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
