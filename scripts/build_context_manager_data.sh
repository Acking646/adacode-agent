#!/usr/bin/env bash
set -euo pipefail

TRACE_PATH="${TRACE_PATH:-./examples/demo_project/.adacode/trajectory.jsonl}"
RAW_OUTPUT="${RAW_OUTPUT:-./data/sft/context_manager_sft.raw.jsonl}"
FILTERED_OUTPUT="${FILTERED_OUTPUT:-./data/sft/context_manager_sft.jsonl}"

python -m training.build_sft_dataset \
  --trace "$TRACE_PATH" \
  --output "$RAW_OUTPUT"

python -m training.rejection_sampling \
  --input "$RAW_OUTPUT" \
  --output "$FILTERED_OUTPUT" \
  --min-reward "${MIN_REWARD:-0.0}"

echo "Wrote filtered SFT data to $FILTERED_OUTPUT"

