from __future__ import annotations

import argparse
from pathlib import Path

from .context_manager import ContextManager, TrainedJSONSelectionModel
from .controller import AgentConfig, CodingAgent
from .llm_client import OpenAICompatibleClient
from .memory import MemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AdaCode-Agent on a local workspace.")
    parser.add_argument("task", help="Programming task for the agent.")
    parser.add_argument("--workspace", default=".", help="Workspace the agent may read and edit.")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI-compatible chat model name.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL.")
    parser.add_argument("--llm-timeout", type=int, default=None, help="LLM request timeout in seconds.")
    parser.add_argument("--llm-retries", type=int, default=None, help="LLM request retry count.")
    parser.add_argument("--cm-mode", choices=["rule", "qwen"], default="rule", help="Context manager backend.")
    parser.add_argument("--cm-model", default="qwen3-4b-cm", help="Context manager model name.")
    parser.add_argument("--cm-base-url", default=None, help="OpenAI-compatible context manager base URL.")
    parser.add_argument("--cm-api-key", default="EMPTY", help="Context manager API key; local vLLM can use EMPTY.")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--token-budget", type=int, default=3500)
    parser.add_argument("--trace", default=".adacode/trajectory.jsonl")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    workspace = Path(args.workspace)
    llm_kwargs = {}
    if args.llm_timeout is not None:
        llm_kwargs["timeout"] = args.llm_timeout
    if args.llm_retries is not None:
        llm_kwargs["retries"] = args.llm_retries
    llm = OpenAICompatibleClient(model=args.model, base_url=args.base_url, **llm_kwargs)
    memory = MemoryStore(workspace / ".adacode" / "memory.json")
    context_manager = None
    if args.cm_mode == "qwen":
        cm_llm = OpenAICompatibleClient(model=args.cm_model, api_key=args.cm_api_key, base_url=args.cm_base_url)
        context_manager = ContextManager(
            memory,
            selector=TrainedJSONSelectionModel(cm_llm),
            token_budget=args.token_budget,
        )
    agent = CodingAgent(
        llm,
        AgentConfig(
            workspace=workspace,
            max_steps=args.max_steps,
            trace_path=workspace / args.trace,
            token_budget=args.token_budget,
        ),
        context_manager=context_manager,
    )
    print(agent.run(args.task))


if __name__ == "__main__":
    main()
