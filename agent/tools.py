from __future__ import annotations

import difflib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

from .schema import ToolResult


class ToolError(ValueError):
    """Raised for invalid local tool requests."""


@dataclass
class ToolExecutor:
    workspace: Path
    command_timeout: int = 30
    max_output_chars: int = 12000

    def __post_init__(self) -> None:
        self.workspace = self.workspace.resolve()

    def dispatch(self, name: str, args: dict) -> ToolResult:
        table: Dict[str, Callable[[dict], ToolResult]] = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "run_command": self.run_command,
            "run_tests": self.run_tests,
            "finish": self.finish,
        }
        if name not in table:
            return ToolResult(False, f"Unknown action: {name}")
        try:
            return table[name](args)
        except Exception as exc:
            return ToolResult(False, f"{type(exc).__name__}: {exc}")

    def _safe_path(self, raw_path: str) -> Path:
        if not raw_path:
            raise ToolError("Path is required.")
        path = (self.workspace / raw_path).resolve()
        if path != self.workspace and self.workspace not in path.parents:
            raise ToolError(f"Path escapes workspace: {raw_path}")
        return path

    def _trim(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        omitted = len(text) - self.max_output_chars
        return text[: self.max_output_chars] + f"\n...[truncated {omitted} chars]"

    def list_files(self, args: dict) -> ToolResult:
        root = self._safe_path(args.get("path", "."))
        max_files = int(args.get("max_files", 200))
        if not root.exists():
            raise ToolError(f"Path does not exist: {root.relative_to(self.workspace)}")

        files: List[str] = []
        if root.is_file():
            files.append(str(root.relative_to(self.workspace)))
        else:
            ignored = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
            for current, dirs, names in os.walk(root):
                dirs[:] = [d for d in dirs if d not in ignored]
                for name in names:
                    rel = Path(current, name).resolve().relative_to(self.workspace)
                    files.append(str(rel).replace("\\", "/"))
                    if len(files) >= max_files:
                        return ToolResult(True, "\n".join(files), {"truncated": True})
        return ToolResult(True, "\n".join(files) or "(no files)")

    def read_file(self, args: dict) -> ToolResult:
        path = self._safe_path(args.get("path", ""))
        start_line = int(args.get("start_line", 1))
        max_lines = int(args.get("max_lines", 240))
        if not path.is_file():
            raise ToolError(f"Not a file: {path.relative_to(self.workspace)}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, start_line - 1)
        selected = lines[start : start + max_lines]
        numbered = [f"{idx + start + 1:04d}: {line}" for idx, line in enumerate(selected)]
        return ToolResult(
            True,
            self._trim("\n".join(numbered)),
            {"path": str(path.relative_to(self.workspace)), "total_lines": len(lines)},
        )

    def write_file(self, args: dict) -> ToolResult:
        path = self._safe_path(args.get("path", ""))
        content = args.get("content")
        if not isinstance(content, str):
            raise ToolError("write_file requires string content.")
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        path.write_text(content, encoding="utf-8")
        diff = "\n".join(
            difflib.unified_diff(
                old.splitlines(),
                content.splitlines(),
                fromfile=f"a/{path.relative_to(self.workspace)}",
                tofile=f"b/{path.relative_to(self.workspace)}",
                lineterm="",
            )
        )
        return ToolResult(True, self._trim(diff or "File written without content changes."))

    def edit_file(self, args: dict) -> ToolResult:
        path = self._safe_path(args.get("path", ""))
        old = args.get("old")
        new = args.get("new")
        replace_all = bool(args.get("replace_all", False))
        if not isinstance(old, str) or not isinstance(new, str):
            raise ToolError("edit_file requires string old and new fields.")
        if not path.is_file():
            raise ToolError(f"Not a file: {path.relative_to(self.workspace)}")
        content = path.read_text(encoding="utf-8", errors="replace")
        count = content.count(old)
        if count == 0:
            raise ToolError("Old text not found.")
        if count > 1 and not replace_all:
            raise ToolError(f"Old text appears {count} times; set replace_all=true or use a more specific snippet.")
        updated = content.replace(old, new) if replace_all else content.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        diff = "\n".join(
            difflib.unified_diff(
                content.splitlines(),
                updated.splitlines(),
                fromfile=f"a/{path.relative_to(self.workspace)}",
                tofile=f"b/{path.relative_to(self.workspace)}",
                lineterm="",
            )
        )
        return ToolResult(True, self._trim(diff), {"replacements": count if replace_all else 1})

    def run_command(self, args: dict) -> ToolResult:
        command = args.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ToolError("run_command requires command as a list of strings.")
        cwd = self._safe_path(args.get("cwd", "."))
        if not cwd.is_dir():
            raise ToolError(f"cwd is not a directory: {cwd.relative_to(self.workspace)}")
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(args.get("timeout", self.command_timeout)),
            shell=False,
        )
        output = self._trim(completed.stdout)
        return ToolResult(completed.returncode == 0, output, {"returncode": completed.returncode})

    def run_tests(self, args: dict) -> ToolResult:
        command = args.get("command", ["python", "-m", "pytest", "-q"])
        return self.run_command({"command": command, "cwd": args.get("cwd", "."), "timeout": args.get("timeout", self.command_timeout)})

    def finish(self, args: dict) -> ToolResult:
        summary = args.get("summary", "")
        return ToolResult(True, str(summary), {"finished": True})
