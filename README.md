# AdaCode-Agent

A self-built coding agent with a trainable context manager.

## Goal

This project implements a lightweight coding agent that can read files, edit code,
run local commands, and iterate on programming tasks through structured model
actions.

The main research-oriented feature is an AdaCom-inspired context manager. Instead
of appending the full interaction history, the agent builds candidate context
items, maintains structured memory cards, and uses a trained small model to
select compact, task-relevant context before each model call.

## Compliance Notes

- No existing agent product is wrapped.
- No agent framework or agent SDK is used.
- Model APIs are used only for language model inference.
- File operations, command execution, context management, action parsing, loop
  control, and error handling are implemented locally.
- API keys and credentials must be provided through environment variables or
  ignored local config files.

## Quick Start

Install the optional test dependency:

```bash
pip install -r requirements.txt
```

Run unit tests:

```bash
python -m pytest -q
```

Run standard-library smoke tests:

```bash
python tests/smoke_test.py
```

Run a deterministic no-API demo:

```bash
python -m agent.demo
```

Run the agent on a workspace with an OpenAI-compatible model:

```bash
set OPENAI_API_KEY=your_key
set OPENAI_BASE_URL=https://api.openai.com/v1
python -m agent.main "Fix the project so tests pass." --workspace examples/demo_project --model gpt-4o-mini
```

For DeepSeek, Qwen, or other compatible providers, set `OPENAI_BASE_URL` and
`--model` to the provider's values.

Example with SiliconFlow:

```bash
set SILICONFLOW_API_KEY=your_key
set OPENAI_BASE_URL=https://api.siliconflow.cn/v1
python -m agent.main "Fix the project so tests pass." --workspace examples/demo_project --model deepseek-ai/DeepSeek-V4-Flash
```

Do not put real API keys in source files, README files, videos, or commits.

## Modules

- `agent/controller.py`: agent loop and termination control
- `agent/tools.py`: local file and command tools
- `agent/parser.py`: structured JSON action parsing
- `agent/context_manager.py`: context selection and compression
- `agent/memory.py`: CRUD memory cards
- `training/train_manager.py`: SFT for the context manager
- `benchmark/run_benchmark.py`: mini coding benchmark evaluation
- `docs/provider_setup.md`: OpenAI-compatible provider configuration

## Context Manager Training

The planned trained manager is `Qwen3-0.6B` with LoRA SFT. It learns JSON context
selection rather than code editing:

```json
{
  "keep": ["task_goal", "mem_0001", "error_0002"],
  "drop": ["old_stdout_0001"],
  "update_memory": [],
  "reason": "Keep the failed test and relevant file path."
}
```

Build bootstrapped SFT data from trajectories:

```bash
python -m training.build_sft_dataset --trace examples/demo_project/.adacode/trajectory.jsonl --output data/sft/context_manager_sft.jsonl
```

Train the optional manager adapter:

```bash
python -m training.train_manager --model Qwen/Qwen3-0.6B --data data/sft/context_manager_sft.jsonl
```

## Evaluation Plan

The main benchmark is `MiniCodeBench-CM`, a small controlled set of coding tasks
with tests. SWE-Bench Lite or Verified can be used later as a smoke test for
real-world issue repair, but not as the main short-term training set.

Compare these settings:

- Full history
- Sliding window
- Rule-based context manager
- SFT context manager

Metrics:

- pass rate
- average steps
- average prompt tokens
- compression ratio
- JSON parse error rate
- critical information drop rate
