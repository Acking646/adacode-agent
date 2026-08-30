from __future__ import annotations

import argparse
from pathlib import Path

from .controller import AgentConfig, CodingAgent
from .llm_client import OpenAICompatibleClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AdaCode-Agent on a local workspace.")
    parser.add_argument("task", help="Programming task for the agent.")
    parser.add_argument("--workspace", default=".", help="Workspace the agent may read and edit.")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI-compatible chat model name.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL.")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--token-budget", type=int, default=3500)
    parser.add_argument("--trace", default=".adacode/trajectory.jsonl")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    workspace = Path(args.workspace)
    llm = OpenAICompatibleClient(model=args.model, base_url=args.base_url)
    agent = CodingAgent(
        llm,
        AgentConfig(
            workspace=workspace,
            max_steps=args.max_steps,
            trace_path=workspace / args.trace,
            token_budget=args.token_budget,
        ),
    )
    print(agent.run(args.task))


if __name__ == "__main__":
    main()

