from agent.parser import parse_action


def test_parse_plain_json_action():
    action = parse_action('{"thought":"inspect","action":"read_file","args":{"path":"a.py"}}')
    assert action.name == "read_file"
    assert action.args["path"] == "a.py"


def test_parse_fenced_json_action():
    action = parse_action('```json\n{"action":"finish","args":{"summary":"done"}}\n```')
    assert action.name == "finish"

