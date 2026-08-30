# Open Data Experiment Plan

This project uses open software-engineering datasets to train and evaluate a
context manager for a self-built coding agent.

## Recommended Datasets

1. SWE-smith trajectories
   - Use for SFT data.
   - Contains agent trajectories from synthetic software-engineering tasks.
   - Convert trajectory turns into context-selection samples.

2. SWE-smith task instances
   - Use for additional training/dev tasks.
   - Good for generating more local trajectories with this agent.

3. SWE-Bench Verified / Lite
   - Use for final smoke-test evaluation.
   - Do not use as the first training source because Docker evaluation is heavy
     and failures have many confounders.

4. BugsInPy++
   - Optional Python-only repair benchmark.
   - Useful when a lighter bug checkout/test workflow is preferred.

## Metrics

- Resolve rate / pass rate: percentage of tasks whose tests pass after agent edits.
- Avg prompt tokens: average input context length.
- Compression ratio: 1 - managed_tokens / full_history_tokens.
- Avg steps: average tool-use iterations per task.
- JSON validity: percentage of manager outputs that parse as valid JSON.
- Critical-info retention: whether task goal, failing test, file path, function
  name, and recent error are preserved.
- Cost proxy: total input/output tokens or API cost estimate.

## Ablations

Compare:

1. Full History
2. Sliding Window
3. Rule Context Manager
4. Qwen3-4B SFT Context Manager

The core claim is not that this small project beats leaderboard systems. The
claim is that a trained context manager keeps less but more useful context for a
coding agent.

## Download

```bash
pip install datasets huggingface_hub
DATA_ROOT=./data/open bash scripts/download_open_datasets.sh
```

For SWE-Bench evaluation:

```bash
git clone https://github.com/SWE-bench/SWE-bench.git ../SWE-bench
cd ../SWE-bench
pip install -e .
swebench eval verified --gold -i sympy__sympy-20590 --run-id validate-gold
```

