from pathlib import Path

from agent.tools import ToolExecutor


def test_edit_file(tmp_path: Path):
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = ToolExecutor(tmp_path).dispatch("edit_file", {"path": "a.py", "old": "1", "new": "2"})
    assert result.ok
    assert path.read_text(encoding="utf-8") == "x = 2\n"


def test_reject_path_escape(tmp_path: Path):
    result = ToolExecutor(tmp_path).dispatch("read_file", {"path": "../secret.txt"})
    assert not result.ok

