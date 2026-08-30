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

## Planned Modules

- `agent/controller.py`: agent loop and termination control
- `agent/tools.py`: local file and command tools
- `agent/parser.py`: structured JSON action parsing
- `agent/context_manager.py`: context selection and compression
- `agent/memory.py`: CRUD memory cards
- `training/train_manager.py`: SFT for the context manager
- `benchmark/run_benchmark.py`: mini coding benchmark evaluation

