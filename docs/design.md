# Design

AdaCode-Agent has two separated components:

1. The self-built coding agent executes local programming work.
2. The context manager selects compact context for the next model call.

The language model never receives direct filesystem access. It only returns a
JSON action. The local controller parses the action, checks workspace safety, and
executes the corresponding tool.

## Agent Loop

```text
task
-> context manager assembles prompt
-> LLM returns JSON action
-> parser validates action
-> local tool executor runs action
-> observation is appended to history
-> memory is updated from failures
-> repeat or finish
```

## Context Manager

The manager builds candidates from:

- the original task
- active memory cards
- recent tool observations
- recent assistant actions
- relevant code/test snippets

The default selector is a local reward scorer. A SFT manager can replace it by
serving a fine-tuned Qwen3-4B model behind an OpenAI-compatible endpoint.

## Training Target

The SFT model learns this JSON schema:

```json
{
  "keep": ["task_goal", "mem_0001", "tool_0003"],
  "drop": ["old_stdout_0001"],
  "update_memory": [
    {
      "id": "mem_0002",
      "status": "obsolete",
      "content": "Previous hypothesis is outdated."
    }
  ],
  "reason": "The selected context keeps the failing test and relevant function."
}
```

This keeps training focused on context management rather than delegating coding
or tool execution to a framework.
