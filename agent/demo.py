from __future__ import annotations

import tempfile
from pathlib import Path

from .controller import AgentConfig, CodingAgent
from .llm_client import ScriptedClient


def main() -> None:
    """Run a deterministic end-to-end demo without an external LLM API."""

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        target = workspace / "demo.py"
        target.write_text("def greet():\n    return 'helo'\n", encoding="utf-8")

        llm = ScriptedClient(
            [
                '{"thought":"Inspect the target file.","action":"read_file","args":{"path":"demo.py"}}',
                (
                    '{"thought":"Fix the typo in the return value.",'
                    '"action":"edit_file","args":{"path":"demo.py","old":"helo","new":"hello"}}'
                ),
                '{"thought":"The edit is complete.","action":"finish","args":{"summary":"Changed helo to hello."}}',
            ]
        )
        agent = CodingAgent(llm, AgentConfig(workspace=workspace, max_steps=3))
        print(agent.run("Fix the greeting typo."))
        print(target.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main()

