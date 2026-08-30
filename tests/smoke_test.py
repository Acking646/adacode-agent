from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.controller import AgentConfig, CodingAgent
from agent.llm_client import ScriptedClient
from agent.parser import parse_action
from agent.tools import ToolExecutor


def main() -> None:
    action = parse_action(json.dumps({"action": "finish", "args": {"summary": "ok"}}))
    assert action.name == "finish"

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        file_path = workspace / "a.py"
        file_path.write_text("x = 1\n", encoding="utf-8")
        result = ToolExecutor(workspace).dispatch("edit_file", {"path": "a.py", "old": "1", "new": "2"})
        assert result.ok
        assert file_path.read_text(encoding="utf-8") == "x = 2\n"

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        target = workspace / "demo.py"
        target.write_text("value = 'old'\n", encoding="utf-8")
        llm = ScriptedClient(
            [
                '{"action":"read_file","args":{"path":"demo.py"}}',
                '{"action":"edit_file","args":{"path":"demo.py","old":"old","new":"new"}}',
                '{"action":"finish","args":{"summary":"done"}}',
            ]
        )
        agent = CodingAgent(llm, AgentConfig(workspace=workspace, max_steps=3))
        assert agent.run("change old to new") == "done"
        assert "new" in target.read_text(encoding="utf-8")

    print("smoke tests passed")


if __name__ == "__main__":
    main()
